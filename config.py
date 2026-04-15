from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    SUPER_ADMIN_ID: int = int(os.getenv("SUPER_ADMIN_ID", "0"))

    DATABASE_URL: str = "sqlite+aiosqlite:///data/voicebot.db"

    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "medium")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    FREE_MESSAGES_LIMIT: int = int(os.getenv("FREE_MESSAGES_LIMIT", "5"))
    FREE_MINUTES_LIMIT: float = float(os.getenv("FREE_MINUTES_LIMIT", "10.0"))

    PER_MESSAGE_STARS: int = int(os.getenv("PER_MESSAGE_STARS", "1"))
    BUNDLE_STARS: int = int(os.getenv("BUNDLE_STARS", "25"))
    BUNDLE_MESSAGES: int = int(os.getenv("BUNDLE_MESSAGES", "30"))

    SUPPORTED_LANGUAGES = ["ru", "en", "zh", "es"]
    DEFAULT_LANGUAGE = "ru"

    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"


settings = Settings()
