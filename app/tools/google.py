"""Google Calendar et Drive via OAuth 2.0 (refresh token d'un compte de test, stocké en secret)."""

import asyncio
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import ToolError, get_settings

# Permissions minimales : événements de l'agenda + lecture seule de Drive.
# Le code restreint en plus l'agent à un agenda et un dossier Drive de test (voir _cal / _root_folder).
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]
MAX_DOC_CHARS = 8000


def _credentials() -> Credentials:
    s = get_settings()
    if s.missing("google_client_id", "google_client_secret", "google_refresh_token"):
        raise ToolError("Google n'est pas configuré (GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN).")
    creds = Credentials(
        token=None, refresh_token=s.google_refresh_token, client_id=s.google_client_id,
        client_secret=s.google_client_secret, token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    try:
        creds.refresh(Request())
    except GoogleAuthError as exc:
        raise ToolError("Autorisation Google refusée ou expirée : relancer scripts/google_login.py.") from exc
    return creds


def _service(api: str, version: str):
    return build(api, version, credentials=_credentials(), cache_discovery=False)


async def _run(fn, *args):
    """Exécute un appel Google bloquant dans un thread et traduit les erreurs."""
    try:
        return await asyncio.to_thread(fn, *args)
    except HttpError as exc:
        raise ToolError(f"Erreur Google {exc.status_code} : {exc._get_reason()}") from exc


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def _parse(dt: str) -> datetime:
    try:
        d = datetime.fromisoformat(dt)
    except ValueError as exc:
        raise ToolError(f"Date/heure invalide : {dt!r} (format ISO 8601 attendu, ex. 2026-10-23T14:00).") from exc
    return d if d.tzinfo else d.replace(tzinfo=_tz())


def _fmt_event(e: dict) -> str:
    start = e["start"].get("dateTime", e["start"].get("date"))
    end = e["end"].get("dateTime", e["end"].get("date"))
    extra = f" — {e['location']}" if e.get("location") else ""
    return f"[id={e['id']}] {e.get('summary', '(sans titre)')} : {start} → {end}{extra}"


def _cal() -> str:
    """Agenda autorisé : un agenda de test dédié, jamais l'agenda principal par défaut."""
    cid = get_settings().google_calendar_id
    if not cid:
        raise ToolError("GOOGLE_CALENDAR_ID n'est pas configuré : l'agent n'accède qu'à un agenda de test dédié.")
    return cid


def _root_folder() -> str:
    root = get_settings().google_drive_folder_id
    if not root:
        raise ToolError("GOOGLE_DRIVE_FOLDER_ID n'est pas configuré : l'agent n'accède qu'à un dossier Drive de test.")
    return root


def _allowed_folders(drive) -> list[str]:
    """Dossier racine autorisé et ses sous-dossiers (3 niveaux, 60 dossiers maximum)."""
    ids = [_root_folder()]
    frontier = list(ids)
    for _ in range(3):
        if not frontier:
            break
        parents = " or ".join(f"'{f}' in parents" for f in frontier)
        res = drive.files().list(
            q=f"({parents}) and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            pageSize=100, fields="files(id)",
        ).execute()
        frontier = [f["id"] for f in res.get("files", []) if f["id"] not in ids]
        ids = (ids + frontier)[:60]
    return ids


def _in_allowed_folder(drive, file_id: str) -> bool:
    root, current = _root_folder(), file_id
    for _ in range(8):
        if current == root:
            return True
        parents = drive.files().get(fileId=current, fields="parents").execute().get("parents", [])
        if not parents:
            return False
        current = parents[0]
    return False


# ---------------------------------------------------------------- Calendar

def _list_events(time_min: str, time_max: str, query: str | None) -> list[dict]:
    res = _service("calendar", "v3").events().list(
        calendarId=_cal(), timeMin=time_min, timeMax=time_max, q=query,
        singleEvents=True, orderBy="startTime", maxResults=50,
    ).execute()
    return res.get("items", [])


async def list_calendar_events(start: str, end: str, query: str | None = None) -> str:
    """Liste ou recherche les événements Google Calendar entre deux dates ISO 8601 (start inclus, end exclu).
    `query` filtre par mot-clé. Pour « demain », passer start=demain 00:00 et end=après-demain 00:00."""
    items = await _run(_list_events, _parse(start).isoformat(), _parse(end).isoformat(), query)
    return "\n".join(_fmt_event(e) for e in items) or "Aucun événement sur cette période."


def _insert(body: dict) -> dict:
    return _service("calendar", "v3").events().insert(calendarId=_cal(), body=body).execute()


async def create_calendar_event(
    title: str, start: str, end: str | None = None, description: str = "", location: str = "",
) -> str:
    """Crée un événement Google Calendar. `end` par défaut : start + 1 h. Dates en ISO 8601."""
    s = _parse(start)
    e = _parse(end) if end else s + timedelta(hours=1)
    if e <= s:
        raise ToolError("La fin de l'événement doit être après son début.")
    tz = get_settings().timezone
    body = {
        "summary": title, "description": description, "location": location,
        "start": {"dateTime": s.isoformat(), "timeZone": tz},
        "end": {"dateTime": e.isoformat(), "timeZone": tz},
    }
    ev = await _run(_insert, body)
    return f"Événement créé : {_fmt_event(ev)}"


def _patch(event_id: str, body: dict) -> dict:
    return _service("calendar", "v3").events().patch(calendarId=_cal(), eventId=event_id, body=body).execute()


async def update_calendar_event(
    event_id: str, title: str | None = None, start: str | None = None, end: str | None = None,
    description: str | None = None, location: str | None = None,
) -> str:
    """Modifie un événement existant (identifié par son id, obtenu via list_calendar_events). Seuls les champs fournis changent."""
    tz = get_settings().timezone
    body: dict = {}
    if title is not None:
        body["summary"] = title
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if start:
        body["start"] = {"dateTime": _parse(start).isoformat(), "timeZone": tz}
    if end:
        body["end"] = {"dateTime": _parse(end).isoformat(), "timeZone": tz}
    if not body:
        raise ToolError("Aucun champ à modifier.")
    return f"Événement modifié : {_fmt_event(await _run(_patch, event_id, body))}"


def _delete(event_id: str) -> None:
    _service("calendar", "v3").events().delete(calendarId=_cal(), eventId=event_id).execute()


async def delete_calendar_event(event_id: str) -> str:
    """Supprime définitivement un événement (identifié par son id obtenu via list_calendar_events)."""
    await _run(_delete, event_id)
    return f"Événement {event_id} supprimé."


# ------------------------------------------------------------------- Drive

def _search(query: str) -> list[dict]:
    safe = query.replace("\\", "\\\\").replace("'", "\\'")
    drive = _service("drive", "v3")
    parents = " or ".join(f"'{f}' in parents" for f in _allowed_folders(drive))
    q = f"(name contains '{safe}' or fullText contains '{safe}') and ({parents}) and trashed = false"
    res = drive.files().list(
        q=q, pageSize=10, fields="files(id,name,mimeType,modifiedTime,webViewLink)", orderBy="modifiedTime desc",
    ).execute()
    return res.get("files", [])


async def search_drive_files(query: str) -> str:
    """Recherche des fichiers Google Drive par nom ou contenu. Renvoie id, nom, type et lien."""
    files = await _run(_search, query)
    return "\n".join(
        f"[id={f['id']}] {f['name']} ({f['mimeType']}, modifié {f['modifiedTime'][:10]}) {f.get('webViewLink', '')}"
        for f in files
    ) or "Aucun fichier trouvé."


def _read(file_id: str) -> str:
    drive = _service("drive", "v3")
    if not _in_allowed_folder(drive, file_id):
        raise ToolError("Ce fichier est hors du dossier Drive autorisé pour l'agent.")
    meta = drive.files().get(fileId=file_id, fields="name,mimeType").execute()
    mime = meta["mimeType"]
    if mime.startswith("application/vnd.google-apps."):
        if mime.endswith(("document", "presentation")):
            req = drive.files().export_media(fileId=file_id, mimeType="text/plain")
        elif mime.endswith("spreadsheet"):
            req = drive.files().export_media(fileId=file_id, mimeType="text/csv")
        else:
            raise ToolError(f"Type Google non lisible : {mime}")
    elif mime.startswith("text/") or mime in ("application/json", "application/xml"):
        req = drive.files().get_media(fileId=file_id)
    else:
        raise ToolError(f"Type de fichier non pris en charge ({mime}) : seuls Google Docs/Sheets/Slides et les fichiers texte sont lisibles.")
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    text = buf.getvalue().decode("utf-8", errors="replace")
    cut = "\n[… contenu tronqué]" if len(text) > MAX_DOC_CHARS else ""
    return f"# {meta['name']}\n{text[:MAX_DOC_CHARS]}{cut}"


async def read_drive_file(file_id: str) -> str:
    """Lit le contenu texte d'un fichier Drive (Google Docs, Sheets, Slides ou fichier texte) à partir de son id."""
    return await _run(_read, file_id)
