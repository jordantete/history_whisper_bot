import os, json
from src.logger import LOGGER


class Utils:
    @staticmethod
    def get_environment_variable(env_var: str):
        try:
            return os.environ[env_var]
        except KeyError:
            LOGGER.error(f"Environment variable: {env_var} not found")
            return None

    @staticmethod
    def load_localizable_data(file_path="src/localizable.json"):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def localize(key, language, localizable_data):
        if language in localizable_data and key in localizable_data[language]:
            return localizable_data[language][key]
        LOGGER.error(f"Missing translation for '{key}' in '{language}'")
        return ""
