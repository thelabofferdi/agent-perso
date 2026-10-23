"""Notion : recherche, lecture, création et ajout de contenu dans des pages."""

import httpx

from app.config import ToolError, get_settings

API = "https://api.notion.com/v1"
MAX_CHARS = 8000


def _headers() -> dict:
    s = get_settings()
    if s.missing("notion_token"):
        raise ToolError("NOTION_TOKEN n'est pas configuré.")
    return {"Authorization": f"Bearer {s.notion_token}", "Notion-Version": "2022-06-28"}


async def _call(method: str, path: str, **kw) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.request(method, f"{API}{path}", headers=_headers(), **kw)
    except httpx.HTTPError as exc:
        raise ToolError(f"Notion injoignable : {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        msg = resp.json().get("message", resp.text[:200]) if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
        raise ToolError(f"Erreur Notion {resp.status_code} : {msg}")
    return resp.json()


def _title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t["plain_text"] for t in prop["title"]) or "(sans titre)"
    return "(sans titre)"


def _paragraphs(text: str) -> list[dict]:
    return [
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk[:2000]}}]}}
        for chunk in text.split("\n") if chunk.strip()
    ]


async def search_notion(query: str = "") -> str:
    """Recherche des pages Notion par mot-clé (titre). Sans mot-clé, liste les pages récentes partagées avec l'intégration."""
    data = await _call("POST", "/search", json={
        "query": query, "page_size": 10,
        "filter": {"property": "object", "value": "page"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
    })
    return "\n".join(
        f"[id={p['id']}] {_title(p)} (modifiée {p['last_edited_time'][:10]}) {p['url']}" for p in data["results"]
    ) or "Aucune page trouvée (la page doit être partagée avec l'intégration Notion)."


async def read_notion_page(page_id: str) -> str:
    """Lit le contenu texte d'une page Notion à partir de son id."""
    page = await _call("GET", f"/pages/{page_id}")
    blocks = await _call("GET", f"/blocks/{page_id}/children", params={"page_size": 100})
    lines = []
    for b in blocks["results"]:
        rich = b.get(b["type"], {}).get("rich_text")
        if rich:
            lines.append("".join(t["plain_text"] for t in rich))
    text = "\n".join(lines)
    cut = "\n[… contenu tronqué]" if len(text) > MAX_CHARS else ""
    return f"# {_title(page)}\n{text[:MAX_CHARS]}{cut}"


async def create_notion_page(title: str, content: str = "", parent_page_id: str | None = None) -> str:
    """Crée une page Notion (sous la page parent de test par défaut) avec le contenu texte fourni."""
    parent = parent_page_id or get_settings().notion_parent_page_id
    if not parent:
        raise ToolError("NOTION_PARENT_PAGE_ID n'est pas configuré et aucun parent n'a été fourni.")
    page = await _call("POST", "/pages", json={
        "parent": {"page_id": parent},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
        "children": _paragraphs(content)[:100],
    })
    return f"Page créée : [id={page['id']}] {title} {page['url']}"


async def append_to_notion_page(page_id: str, content: str) -> str:
    """Ajoute du texte à la fin d'une page Notion existante (modification d'une note)."""
    children = _paragraphs(content)
    if not children:
        raise ToolError("Le contenu à ajouter est vide.")
    await _call("PATCH", f"/blocks/{page_id}/children", json={"children": children[:100]})
    return f"Contenu ajouté à la page {page_id}."
