import os, json
from src.logger import LOGGER

class Utils:
    @classmethod
    def get_environment_varibale(self, env_var: str):
        if os.path.exists("secrets.json"):
            secrets = self.__read_secrets()
            return secrets[env_var]
        else:
            try:
                environment_var = os.environ[env_var]
                return environment_var
            except KeyError:
                LOGGER.error(f"Environment variable: {env_var} not found")

    def __read_secrets() -> dict:
        filename = os.path.join("secrets.json")
        try:
            with open(filename, mode="r") as f:
                return json.loads(f.read())
        except FileNotFoundError:
            LOGGER.error("File which handle secrets not found")
            return {}

    def load_localizable_data(file_path="src/localizable.json"):
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data

    def localize(key, language, localizable_data):
        if language in localizable_data and key in localizable_data[language]:
            return localizable_data[language][key]
        else:
            LOGGER.error(f"Missing translation for '{key}' in '{language}'")
            return ""