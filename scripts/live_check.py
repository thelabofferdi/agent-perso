"""Vérifie chaque outil avec les vraies clés de .env (lecture seule, aucun envoi)."""
import asyncio
import sys

from app.config import ToolError, get_settings
from app.tools import google, notion, web

CHECKS = {
    "tavily": lambda: web.web_search("dernières actualités intelligence artificielle", 3, news=True),
    "meteo": lambda: web.get_current_weather("Paris"),
    "meteo_prev": lambda: web.get_weather_forecast("Lagos", 2),
    "notion": lambda: notion.search_notion(""),
    "calendar": lambda: google.list_calendar_events("2026-10-22T00:00", "2026-10-30T00:00"),
    "drive": lambda: google.search_drive_files("a"),
}


async def main(names):
    for name in names or CHECKS:
        try:
            out = await CHECKS[name]()
            print(f"[OK ] {name}: {out[:160]!r}")
        except ToolError as e:
            print(f"[KO ] {name}: {e}")


asyncio.run(main(sys.argv[1:]))
