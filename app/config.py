"""Configuration : tout vient des variables d'environnement, rien n'est écrit en dur."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # LLM (RodiumAI, compatible OpenAI)
    rodium_api_key: str
    rodium_base_url: str
    model_name: str
    # Services
    tavily_api_key: str
    weather_api_key: str
    notion_token: str
    notion_parent_page_id: str
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    google_calendar_id: str
    google_drive_folder_id: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    # App
    timezone: str
    access_code: str

    def missing(self, *names: str) -> list[str]:
        return [n.upper() for n in names if not getattr(self, n)]


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        rodium_api_key=env("RODIUM_API_KEY", ""),
        rodium_base_url=env("RODIUM_BASE_URL", "https://api.rodiumai.io/v1"),
        model_name=env("RODIUM_MODEL", "anthropic/claude-haiku-5-5"),
        tavily_api_key=env("TAVILY_API_KEY", ""),
        weather_api_key=env("OPENWEATHER_API_KEY", ""),
        notion_token=env("NOTION_TOKEN", ""),
        notion_parent_page_id=env("NOTION_PARENT_PAGE_ID", ""),
        google_client_id=env("GOOGLE_CLIENT_ID", ""),
        google_client_secret=env("GOOGLE_CLIENT_SECRET", ""),
        google_refresh_token=env("GOOGLE_REFRESH_TOKEN", ""),
        google_calendar_id=env("GOOGLE_CALENDAR_ID", ""),
        google_drive_folder_id=env("GOOGLE_DRIVE_FOLDER_ID", ""),
        smtp_host=env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(env("SMTP_PORT", "465")),
        smtp_user=env("SMTP_USER", ""),
        smtp_password=env("SMTP_PASSWORD", ""),
        smtp_from=env("SMTP_FROM", "") or env("SMTP_USER", ""),
        timezone=env("APP_TIMEZONE", "Europe/Paris"),
        access_code=env("APP_ACCESS_CODE", ""),
    )


class ToolError(Exception):
    """Erreur lisible renvoyée au LLM (config manquante, API en échec, saisie invalide)."""
