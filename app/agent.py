"""Agent PydanticAI : le LLM choisit lui-même les outils ; les actions sensibles exigent une approbation."""

import functools
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, DeferredToolRequests, Tool
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import ToolError, get_settings
from app.tools import google, mail, notion, web

# Outils qui modifient le monde réel : exécutés seulement après confirmation explicite de l'utilisateur.
REQUIRES_APPROVAL = {
    mail.send_email,
    google.create_calendar_event,
    google.update_calendar_event,
    google.delete_calendar_event,
}

MAX_OUTPUT_TOKENS = 1500

TOOLS = [
    web.web_search, web.get_current_weather, web.get_weather_forecast,
    google.list_calendar_events, google.create_calendar_event,
    google.update_calendar_event, google.delete_calendar_event,
    mail.send_email,
    notion.search_notion, notion.read_notion_page, notion.create_notion_page, notion.append_to_notion_page,
    google.search_drive_files, google.read_drive_file,
]


def _safe(fn):
    """Convertit les erreurs prévisibles en message lisible par le LLM (qui l'explique à l'utilisateur)."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ToolError as exc:
            return f"ERREUR : {exc}"
    return wrapper


def _instructions() -> str:
    now = datetime.now(ZoneInfo(get_settings().timezone))
    return f"""Tu es un assistant personnel qui AGIT via des outils réels. Date et heure actuelles : {now:%A %d %B %Y, %H:%M} (fuseau {get_settings().timezone}).

Règles :
- Choisis les outils selon la demande ; combine-en plusieurs si besoin (ex. agenda → notes Notion → actualités → synthèse). N'invente jamais un résultat : appelle l'outil.
- Réponds dans la langue de l'utilisateur. Pour la recherche web, cite les liens des sources utilisées.
- Agenda : convertis « demain », « vendredi »… en dates ISO à partir de la date actuelle. Pour modifier/supprimer, retrouve d'abord l'événement et son id avec list_calendar_events.
- E-mail : si destinataire, objet ou contenu manque, demande-le. Sinon appelle send_email avec le texte complet : l'utilisateur confirmera dans l'interface avant l'envoi.
- Les créations/modifications/suppressions d'événements et les envois d'e-mails nécessitent la confirmation de l'utilisateur, gérée par l'interface.
- Si un outil renvoie « ERREUR », explique simplement le problème et propose une alternative. Si une information manque, pose la question."""


def build_agent() -> Agent:
    s = get_settings()
    model = OpenAIChatModel(
        s.model_name, provider=OpenAIProvider(base_url=s.rodium_base_url, api_key=s.rodium_api_key or "missing"),
    )
    tools = [Tool(_safe(fn), requires_approval=fn in REQUIRES_APPROVAL) for fn in TOOLS]
    return Agent(
        model, tools=tools, instructions=_instructions,
        output_type=[str, DeferredToolRequests], retries=2,
        # La passerelle réserve le coût maximal d'une réponse : sans plafond, le solde est bloqué (402).
        model_settings=ModelSettings(max_tokens=MAX_OUTPUT_TOKENS),
    )
