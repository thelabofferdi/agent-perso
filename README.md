# Agent IA personnel (PydanticAI + tool calling)

Agent qui **agit** : recherche web (Tavily), météo (OpenWeather), Google Calendar, e-mail (SMTP), Notion, Google Drive.
LLM via RodiumAI (API compatible OpenAI). Le modèle choisit lui-même les outils ; créations/modifications/suppressions
d'événements et envois d'e-mails ne s'exécutent qu'après un clic **Confirmer** (`requires_approval` de PydanticAI,
appliqué côté serveur, pas seulement dans le prompt).

## Lancer en local
```bash
cp .env.example .env   # remplir les clés
uv run uvicorn app.main:app --reload --port 8080
uv run pytest
```

## Configurer les services (comptes de TEST)
| Service | Variable(s) |
|---|---|
| RodiumAI | `RODIUM_API_KEY` (clé `rd_sk_…`), `RODIUM_MODEL` (défaut `anthropic/claude-haiku-5-5`, ~10x moins cher que gpt-4o) |
| Tavily | `TAVILY_API_KEY` |
| OpenWeather | `OPENWEATHER_API_KEY` |
| Notion | `NOTION_TOKEN` (intégration interne) + `NOTION_PARENT_PAGE_ID`; **partager les pages avec l'intégration** |
| Google | `GOOGLE_CALENDAR_ID` et `GOOGLE_DRIVE_FOLDER_ID` (agenda et dossier de test : l'agent n'accède à rien d'autre), `GOOGLE_CLIENT_ID/SECRET`, puis `uv run python scripts/google_login.py` → `GOOGLE_REFRESH_TOKEN`. Scopes minimaux : `calendar.events`, `drive.readonly` |
| E-mail | `SMTP_USER`, `SMTP_PASSWORD` (mot de passe d'application), `SMTP_HOST/PORT/FROM` |

## Déployer (Docker / machine Linux)
```bash
docker build -t agent-perso .
docker run -p 8080:8080 --env-file .env agent-perso
```
Sans Docker : `uv sync --no-dev` puis `uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`.
Les secrets viennent de variables d'environnement (`.env` non versionné) ; `APP_ACCESS_CODE` (optionnel) protège l'API.
Les conversations sont gardées en mémoire : une seule instance du service.
