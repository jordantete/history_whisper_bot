import os, json
from logger import LOGGER

class Utils:
    @staticmethod
    def get_environment_varibale(env_var: str):
        if os.path.exists("secrets.json"):
            secrets = read_secrets()
            return secrets[env_var]
        else:
            try:
                environment_var = os.environ[env_var]
                return environment_var
            except KeyError:
                LOGGER.error(f"Environment variable: {env_var} not found")

    @staticmethod
    def read_secrets() -> dict:
        filename = os.path.join("secrets.json")
        try:
            with open(filename, mode="r") as f:
                return json.loads(f.read())
        except FileNotFoundError:
            LOGGER.error("File which handle secrets not found")
            return {}