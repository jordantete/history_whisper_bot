import os
import html
import time
from datetime import date, time as dtime
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo

from src.database import Database
from src.subscribers import SubscriberStore
from src.suggestions import SuggestionStore
from src.utils import Utils
from src.logger import LOGGER
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, BotCommand,
                      LinkPreviewOptions)
from telegram.constants import ChatAction, MessageLimit, ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, TypeHandler, ApplicationHandlerStop,
    AIORateLimiter, filters,
)

# ConversationHandler state: waiting for the user's feedback message.
FEEDBACK_WAITING = 0

# When the daily figure is delivered to subscribers (single timezone for now).
DAILY_TIME = dtime(hour=12, minute=0, tzinfo=ZoneInfo("Europe/Paris"))


class Bot:
    # Minimum delay between two feedback submissions forwarded to the owner,
    # per user — protects the owner's chat from a single user flooding it.
    FEEDBACK_COOLDOWN_SECONDS = 30

    def __init__(self, database: Database, subscriber_store: SubscriberStore = None):
        token = Utils.get_environment_variable("TELEGRAM_BOT_TOKEN")
        # AIORateLimiter paces outgoing API calls so a burst of traffic can't
        # trip Telegram's token-wide flood limits (which would mute the bot).
        # post_init publishes the localized command menu + profile descriptions.
        self.application = (
            ApplicationBuilder()
            .token(token)
            .rate_limiter(AIORateLimiter())
            .post_init(self._post_init)
            .build()
        )
        self.database = database
        self.localizable_strings = Utils.load_localizable_data()
        self._feedback_last = {}  # user_id -> monotonic timestamp of last forwarded feedback
        self.subscribers = subscriber_store or SubscriberStore(
            os.environ.get("SUBSCRIBERS_FILE", "subscribers.json"))
        self.suggestions = SuggestionStore(
            os.environ.get("SUGGESTIONS_FILE", "suggestions.json"))
        # Renseigné dans _post_init : sans lui, pas de deep link possible.
        self._bot_username = None

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return Utils.resolve_locale(language_code)

    def _t(self, key: str, update: Update) -> str:
        return Utils.localize(key, self._locale(update), self.localizable_strings)

    def _tl(self, key: str, locale: str) -> str:
        return Utils.localize(key, locale, self.localizable_strings)

    async def _post_init(self, application) -> None:
        """Publish the localized command menu and profile descriptions to
        Telegram once, at startup. Default (no language_code) carries English;
        French is registered explicitly. Shown in the '/' menu and on the
        bot's start screen / profile."""
        # Needed to build share deep links; the button is omitted until it is known.
        self._bot_username = application.bot.username
        menu = ("today", "random", "quote", "subscribe", "unsubscribe", "feedback", "help")
        for locale, language_code in (("en", None), ("fr", "fr")):
            # The display name is Telegram's top in-app search ranking factor, so it
            # carries keywords. Telegram rate-limits name changes, hence the read
            # first / write only on drift — a restart with an unchanged name is a no-op.
            name = self._tl("bot-name", locale)
            current = await application.bot.get_my_name(language_code=language_code)
            if current.name != name:
                try:
                    await application.bot.set_my_name(name, language_code=language_code)
                    LOGGER.info(f"Updated bot name [{locale}]: {name}")
                except TelegramError as error:
                    LOGGER.warning(f"Could not set bot name [{locale}]: {error}")
            commands = [BotCommand(cmd, self._tl(f"cmd-{cmd}", locale)) for cmd in menu]
            await application.bot.set_my_commands(commands, language_code=language_code)
            await application.bot.set_my_short_description(
                self._tl("bot-short-description", locale), language_code=language_code)
            await application.bot.set_my_description(
                self._tl("bot-description", locale), language_code=language_code)
        # Schedule the daily figure delivery to subscribers.
        # misfire_grace_time widens APScheduler's default 1s window: if the event
        # loop is briefly blocked at noon (e.g. a Telegram getUpdates retry storm),
        # the job still fires within the hour instead of being silently dropped.
        if application.job_queue:
            application.job_queue.run_daily(
                self._send_daily, time=DAILY_TIME, name="daily-figure",
                job_kwargs={"misfire_grace_time": 3600})
            LOGGER.info(f"Scheduled daily delivery at {DAILY_TIME}")
        else:
            LOGGER.warning("JobQueue unavailable — daily delivery not scheduled")

    def _figure_bio(self, figure, locale: str) -> str:
        primary = figure.bio_fr if locale == "fr" else figure.bio_en
        secondary = figure.bio_en if locale == "fr" else figure.bio_fr
        return primary or secondary or figure.description or ""

    def _figure_facts(self, figure, locale: str) -> list:
        primary = figure.facts_fr if locale == "fr" else figure.facts_en
        secondary = figure.facts_en if locale == "fr" else figure.facts_fr
        return primary or secondary or []

    @staticmethod
    def _build_card_text(name: str, bio: str, facts, header: str,
                         limit: int = MessageLimit.MAX_TEXT_LENGTH) -> str:
        """Render an HTML card (bold name, italic bio, bold header + bullets).
        All dynamic content is HTML-escaped. Telegram's length limit counts the
        *visible* text (tags/entities excluded), so truncation is budgeted on the
        raw text length while the output carries the markup."""
        def esc(s):
            return html.escape(s, quote=False)

        separator = "\n\n"
        # facts block: visible form drives the budget, html form is emitted.
        facts_visible = ""
        facts_html = ""
        if facts:
            facts_visible = separator + header + "\n" + "\n".join(f"• {f}" for f in facts)
            facts_html = separator + f"<b>{esc(header)}</b>\n" + "\n".join(f"• {esc(f)}" for f in facts)

        name_html = f"<b>{esc(name)}</b>"
        full_visible = len(name) + (len(separator) + len(bio) if bio else 0) + len(facts_visible)
        if full_visible <= limit:
            body = name_html if not bio else f"{name_html}{separator}<i>{esc(bio)}</i>"
            return body + facts_html
        # Over the limit: truncate the bio (visible budget), keep name + facts.
        ellipsis = "…"
        budget = limit - len(name) - len(separator) - len(ellipsis) - len(facts_visible)
        if budget > 0:
            truncated = bio[:budget].rstrip()
            return f"{name_html}{separator}<i>{esc(truncated)}{ellipsis}</i>{facts_html}"
        # No room for any bio: drop it, keep name + facts.
        if len(name) + len(facts_visible) <= limit:
            return name_html + facts_html
        # Last resort: even name + facts exceed the limit. Hard-clamp the visible
        # text to guarantee the invariant, at the cost of formatting/content.
        return esc((name + facts_visible)[:limit])

    @staticmethod
    def _read_more_url(figure, locale: str):
        """Wikidata redirect to the figure's Wikipedia article in the given
        locale, resolved from its Wikidata id (robust to title mismatches).
        Returns None when the figure has no Wikidata id."""
        if not figure.wikidata_id:
            return None
        site = "frwiki" if locale == "fr" else "enwiki"
        return f"https://www.wikidata.org/wiki/Special:GoToLinkedPage?site={site}&itemid={figure.wikidata_id}"

    def _share_url(self, figure, locale: str):
        """Lien vers la feuille de partage native de Telegram, pré-remplie avec
        une accroche et un deep link vers cette figure. Renvoie None tant que
        l'username du bot est inconnu — le bouton est alors simplement omis."""
        if not self._bot_username:
            return None
        deep_link = f"https://t.me/{self._bot_username}?start={Utils.figure_slug(figure.name)}"
        text = self._tl("share-text", locale).format(name=figure.name)
        return f"https://t.me/share/url?url={url_quote(deep_link, safe='')}&text={url_quote(text, safe='')}"

    def _figure_keyboard(self, locale: str, figure) -> InlineKeyboardMarkup:
        rows = [[
            InlineKeyboardButton(self._tl("btn-another", locale), callback_data="random"),
            InlineKeyboardButton(self._tl("btn-today", locale), callback_data="today"),
        ]]
        # Seconde rangée adaptative : « Read more » n'existe que sur les figures
        # à wikidata_id (7 sur 339), le partage sur toutes.
        second = []
        read_more = self._read_more_url(figure, locale)
        if read_more:
            second.append(InlineKeyboardButton(self._tl("btn-read-more", locale), url=read_more))
        share = self._share_url(figure, locale)
        if share:
            second.append(InlineKeyboardButton(self._tl("btn-share", locale), url=share))
        if second:
            rows.append(second)
        return InlineKeyboardMarkup(rows)

    @staticmethod
    def _quote_lang(quote, locale: str) -> str:
        """Langue effectivement servie : celle du lecteur si la citation existe
        dans cette langue, sinon l'autre. Le corpus étant francophone tant que
        la dette de traduction EN n'est pas traitée, un lecteur anglophone
        reçoit le français plutôt que rien."""
        if locale == "fr":
            return "fr" if quote.text_fr else "en"
        return "en" if quote.text_en else "fr"

    @staticmethod
    def _quote_parts(quote, lang: str):
        """Texte et source pris dans la même langue. Les déparier — un texte
        français sous une source anglaise — serait incohérent à la lecture."""
        if lang == "fr":
            return quote.text_fr or "", quote.source_fr or ""
        return quote.text_en or "", quote.source_en or ""

    @staticmethod
    def _build_quote_text(text: str, author: str, source: str, header: str,
                          limit: int = MessageLimit.MAX_TEXT_LENGTH) -> str:
        """Render an HTML quote card. Unlike `_build_card_text`, no arbitration
        is needed between competing blocks: the pipeline caps quote text at 600
        visible characters, so the clamp below only guards against a corpus
        entry edited by hand."""
        def esc(s):
            return html.escape(s, quote=False)

        # Décoration fixe : en-tête, guillemets, tiret cadratin, sauts de ligne.
        overhead = len(header) + len(author) + len(source) + 12
        budget = limit - overhead
        if len(text) > budget:
            text = text[:max(budget - 1, 0)].rstrip() + "…"

        lines = [f"<b>{esc(header)}</b>", "", f"<i>« {esc(text)} »</i>", "",
                 f"— <b>{esc(author)}</b>"]
        if source:
            lines.append(f"<i>{esc(source)}</i>")
        return "\n".join(lines)

    @staticmethod
    def _quote_source_url(quote, lang: str):
        """Page Wikiquote d'où la citation provient. Sert de bouton « Source »
        et vaut attribution CC BY-SA. None quand le titre est absent : le
        bouton est alors simplement omis."""
        title = quote.wikiquote_fr if lang == "fr" else quote.wikiquote_en
        if not title:
            return None
        return f"https://{lang}.wikiquote.org/wiki/{url_quote(title, safe='')}"

    def _quote_share_url(self, quote, lang: str):
        """Feuille de partage native de Telegram, pré-remplie avec la citation
        et un deep link vers elle. Le payload porte le préfixe 'q-' qui le
        distingue d'un slug de figure."""
        if not self._bot_username:
            return None
        deep_link = f"https://t.me/{self._bot_username}?start=q-{quote.id}"
        text, _ = self._quote_parts(quote, lang)
        share_text = self._tl("share-quote-text", lang).format(text=text, author=quote.author)
        return (f"https://t.me/share/url?url={url_quote(deep_link, safe='')}"
                f"&text={url_quote(share_text, safe='')}")

    def _quote_keyboard(self, locale: str, quote, lang: str) -> InlineKeyboardMarkup:
        """`locale` porte les libellés (langue du lecteur), `lang` les liens
        (langue dans laquelle la citation est servie)."""
        rows = [[InlineKeyboardButton(self._tl("btn-another-quote", locale),
                                      callback_data="random_quote")]]
        second = []
        source_url = self._quote_source_url(quote, lang)
        if source_url:
            second.append(InlineKeyboardButton(self._tl("btn-quote-source", locale), url=source_url))
        share = self._quote_share_url(quote, lang)
        if share:
            second.append(InlineKeyboardButton(self._tl("btn-share", locale), url=share))
        if second:
            rows.append(second)
        return InlineKeyboardMarkup(rows)

    async def _deliver_quote(self, context: ContextTypes.DEFAULT_TYPE, chat_id, locale: str, quote) -> None:
        """Envoie une carte citation à un chat donné. Partagée par la commande
        interactive et le job quotidien, comme `_deliver_figure`.

        Aucune image : l'aperçu de lien est explicitement désactivé, sans quoi
        Telegram tenterait de rendre une URL présente dans la source.

        Forbidden (l'utilisateur a bloqué le bot) se propage, pour que les
        appelants puissent réagir."""
        lang = self._quote_lang(quote, locale)
        text, source = self._quote_parts(quote, lang)
        rendered = self._build_quote_text(text, quote.author, source,
                                          self._tl("quote-header", locale))
        await context.bot.send_message(chat_id=chat_id, text=rendered, parse_mode=ParseMode.HTML,
                                       reply_markup=self._quote_keyboard(locale, quote, lang),
                                       link_preview_options=LinkPreviewOptions(is_disabled=True))

    async def _deliver_figure(self, context: ContextTypes.DEFAULT_TYPE, chat_id, locale: str, figure) -> None:
        """Send a rendered figure card to a specific chat in a specific locale.
        Shared by interactive commands and the daily job.

        The portrait rides along as a link preview rather than a photo caption:
        Telegram caps captions at 1024 visible characters but allows 4096 in
        message text, and 64 of the cards did not fit in 1024. Rendering is
        identical (large image above the text) — verified against send_photo.
        The trade-off is that a preview Telegram cannot fetch fails silently,
        where send_photo used to raise; the reader still gets the full card,
        so only the log warning is lost.

        Forbidden (user blocked the bot) propagates so callers can react."""
        bio = self._figure_bio(figure, locale)
        facts = self._figure_facts(figure, locale)
        text = self._build_card_text(figure.name, bio, facts, self._tl("highlights-header", locale))
        preview = (LinkPreviewOptions(url=figure.image_url, prefer_large_media=True, show_above_text=True)
                   if figure.image_url else LinkPreviewOptions(is_disabled=True))
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
                                       reply_markup=self._figure_keyboard(locale, figure),
                                       link_preview_options=preview)

    async def _send_figure(self, update: Update, context: ContextTypes.DEFAULT_TYPE, figure) -> None:
        if not figure:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("no-figures", update))
            return
        await self._deliver_figure(context, update.effective_chat.id, self._locale(update), figure)

    async def _send_daily(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """JobQueue callback: deliver the figure of the day to all subscribers,
        each in their own locale. Subscribers who blocked the bot are dropped."""
        figure = self.database.get_figure_of_the_day(date.today())
        if not figure:
            LOGGER.warning("No figure of the day — skipping daily delivery")
            return
        recipients = self.subscribers.all()
        LOGGER.info(f"Daily delivery starting for {len(recipients)} subscriber(s)")
        sent = 0
        for chat_id, locale in recipients:
            try:
                await self._deliver_figure(context, chat_id, locale, figure)
                sent += 1
            except Forbidden:
                LOGGER.info(f"Subscriber {chat_id} blocked the bot — removing")
                self.subscribers.unsubscribe(chat_id)
            except TelegramError as e:
                LOGGER.warning(f"Daily delivery to {chat_id} failed: {e}")
        LOGGER.info(f"Daily delivery done: {sent}/{len(recipients)} sent")

    async def __group_guard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Runs before every handler. The bot is private-only: in any group /
        supergroup / channel it stays silent, leaves the chat, and stops all
        further handling. No per-user access control — the bot is public."""
        chat = update.effective_chat
        if not chat or chat.type == "private":
            return
        LOGGER.info(f"Non-private chat {chat.id} ({chat.type}) — leaving and ignoring")
        try:
            await context.bot.leave_chat(chat_id=chat.id)
        except Exception as e:
            LOGGER.warning(f"Failed to leave chat {chat.id}: {e}")
        raise ApplicationHandlerStop

    async def __start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Start handler command called")
        # Deep link t.me/<bot>?start=<slug> : Telegram passe le payload en args.
        if context.args:
            await self.__deliver_shared_figure(update, context, context.args[0])
            return
        text = self._t("start-message", update)
        buttons = [
            InlineKeyboardButton("🎲 Random", callback_data="random"),
            InlineKeyboardButton("📅 Today", callback_data="today"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
        reply_markup = InlineKeyboardMarkup([buttons])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

    async def __deliver_shared_figure(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                      payload: str):
        """Sert la figure d'un lien partagé. Le destinataire est un inconnu :
        la ligne de contexte est le seul endroit où on lui dit où il est et
        comment s'abonner. Un slug qui ne résout plus (figure renommée) le
        renvoie sur la figure du jour plutôt que sur une erreur sèche."""
        locale = self._locale(update)
        figure = self.database.get_figure_by_slug(payload)
        if figure:
            intro = self._tl("shared-intro", locale)
        else:
            LOGGER.info(f"Unknown share payload: {payload!r}")
            intro = self._tl("share-unknown", locale)
            figure = self.database.get_figure_of_the_day(date.today())
        await context.bot.send_message(chat_id=update.effective_chat.id, text=intro)
        await self._send_figure(update, context, figure)

    async def __help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Help handler command called")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("help-message", update))

    async def __random_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Random handler command called")
        figure = self.database.get_random_figure()
        await self._send_figure(update, context, figure)

    async def __today_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Today handler command called")
        figure = self.database.get_figure_of_the_day(date.today())
        await self._send_figure(update, context, figure)

    async def _send_quote(self, update: Update, context: ContextTypes.DEFAULT_TYPE, quote) -> None:
        # Envoie une citation, ou le message "pas de citation" si le corpus est vide.
        if not quote:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=self._t("no-quotes", update))
            return
        await self._deliver_quote(context, update.effective_chat.id, self._locale(update), quote)

    async def __quote_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Quote handler command called")
        quote = self.database.get_quote_of_the_day(date.today())
        await self._send_quote(update, context, quote)

    async def __button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        LOGGER.info(f"Button pressed: {query.data}")
        if query.data == "random":
            await self._send_figure(update, context, self.database.get_random_figure())
        elif query.data == "today":
            await self._send_figure(update, context, self.database.get_figure_of_the_day(date.today()))
        elif query.data == "random_quote":
            await self._send_quote(update, context, self.database.get_random_quote())
        elif query.data == "help":
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("help-message", update))

    async def __subscribe_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Subscribe handler command called")
        chat_id = update.effective_chat.id
        newly = self.subscribers.subscribe(chat_id, self._locale(update))
        key = "subscribe-done" if newly else "subscribe-already"
        await context.bot.send_message(chat_id=chat_id, text=self._t(key, update))

    async def __unsubscribe_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Unsubscribe handler command called")
        chat_id = update.effective_chat.id
        was_subscribed = self.subscribers.unsubscribe(chat_id)
        key = "unsubscribe-done" if was_subscribed else "unsubscribe-none"
        await context.bot.send_message(chat_id=chat_id, text=self._t(key, update))

    def _feedback_allowed(self, user_id, now: float) -> bool:
        """Per-user cooldown gate. Returns True (and records `now`) if the user
        may submit feedback; False if they're still within the cooldown window.
        Only allowed submissions update the timestamp, so continuous spam stays
        capped at one forward per cooldown window."""
        last = self._feedback_last.get(user_id)
        if last is not None and now - last < self.FEEDBACK_COOLDOWN_SECONDS:
            return False
        self._feedback_last[user_id] = now
        return True

    async def _forward_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        user = update.effective_user
        if user and not self._feedback_allowed(user.id, time.monotonic()):
            LOGGER.info(f"Feedback from {user.id} throttled (cooldown)")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-cooldown", update))
            return
        owner_chat_id = os.environ.get("OWNER_CHAT_ID")
        if owner_chat_id:
            who = f"@{user.username}" if user and user.username else (str(user.id) if user else "unknown")
            try:
                await context.bot.send_message(chat_id=owner_chat_id, text=f"Feedback from {who}:\n{text}")
            except Exception as e:
                LOGGER.error(f"Failed to forward feedback to owner: {e}")
        else:
            LOGGER.warning("OWNER_CHAT_ID not set — feedback not forwarded")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-thanks", update))

    async def __feedback_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback command called")
        text = " ".join(context.args).strip() if context.args else ""
        if text:
            await self._forward_feedback(update, context, text)
            return ConversationHandler.END
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self._t("feedback-ask", update),
            reply_markup=ForceReply(input_field_placeholder=self._t("feedback-placeholder", update)),
        )
        return FEEDBACK_WAITING

    async def __feedback_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback received via conversation")
        text = (update.message.text or "").strip()
        await self._forward_feedback(update, context, text)
        return ConversationHandler.END

    async def __feedback_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback cancelled")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-cancel", update))
        return ConversationHandler.END

    def _is_owner(self, update: Update) -> bool:
        """Fail closed : sans OWNER_CHAT_ID configuré, personne n'est owner.
        L'inverse ouvrirait /suggest à tous sur un simple oubli de config."""
        owner_chat_id = os.environ.get("OWNER_CHAT_ID")
        if not owner_chat_id:
            LOGGER.warning("OWNER_CHAT_ID not set — /suggest refused")
            return False
        return str(update.effective_chat.id) == str(owner_chat_id)

    async def __suggest_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Empile des noms de figures pour le pipeline de contenu. Owner-only,
        absente du menu publié. Les réponses sont en dur, en français : ce sont
        des messages d'opérateur, pas de la copie produit."""
        if not self._is_owner(update):
            LOGGER.info(f"/suggest ignored for chat {update.effective_chat.id}")
            return

        raw = " ".join(context.args) if context.args else ""
        names = [n.strip() for n in raw.split(",") if n.strip()]
        if not names:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Usage : /suggest Nom, Autre nom, Encore un")
            return

        roster = [f.name for f in self.database.get_all_figures()]
        lines = []
        for name in names:
            near = [r for r in roster if Utils.names_match(name, r)]
            if self.suggestions.add(name):
                # Rapprochement = avertissement, jamais un refus : le roster
                # stocke des formes courtes qui produisent des faux positifs
                # ('Philippe Auguste' contre 'Auguste'). L'humain tranche.
                lines.append(f"⚠️ {name} — ressemble à {', '.join(near)} déjà au roster"
                             if near else f"✅ {name}")
            else:
                lines.append(f"↩️ {name} — déjà en file")

        lines.append(f"\nFile : {self.suggestions.count()}")
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="\n".join(lines))

    def register_handlers(self):
        # Global gate (runs before all group-0 handlers): private-chat-only.
        self.application.add_handler(TypeHandler(Update, self.__group_guard), group=-1)
        self.application.add_handler(CommandHandler('start', self.__start_handler))
        self.application.add_handler(CommandHandler('help', self.__help_handler))
        self.application.add_handler(CommandHandler('random', self.__random_handler))
        self.application.add_handler(CommandHandler('today', self.__today_handler))
        self.application.add_handler(CommandHandler('quote', self.__quote_handler))
        self.application.add_handler(CommandHandler('subscribe', self.__subscribe_handler))
        self.application.add_handler(CommandHandler('unsubscribe', self.__unsubscribe_handler))
        self.application.add_handler(CommandHandler('suggest', self.__suggest_handler))
        self.application.add_handler(ConversationHandler(
            entry_points=[CommandHandler('feedback', self.__feedback_entry)],
            states={FEEDBACK_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.__feedback_receive)]},
            fallbacks=[CommandHandler('cancel', self.__feedback_cancel)],
        ))
        self.application.add_handler(CallbackQueryHandler(self.__button_handler))

    def run(self):
        LOGGER.info("Bot starting in long-polling mode")
        self.register_handlers()
        self.application.run_polling()
