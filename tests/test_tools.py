import httpx
import pytest
import respx

from app.config import ToolError
from app.tools import mail, notion, web


@respx.mock
async def test_web_search_returns_sources():
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(200, json={
        "answer": "Réponse", "results": [{"title": "T", "url": "https://x.io/a", "content": "contenu"}]}))
    out = await web.web_search("ia", news=True)
    assert "https://x.io/a" in out and "Réponse" in out


@respx.mock
async def test_weather_current_and_forecast():
    respx.get("https://api.openweathermap.org/data/2.5/weather").mock(return_value=httpx.Response(200, json={
        "name": "Accra", "sys": {"country": "GH"}, "weather": [{"description": "ciel dégagé"}],
        "main": {"temp": 31, "feels_like": 34, "humidity": 70}, "wind": {"speed": 3}}))
    respx.get("https://api.openweathermap.org/data/2.5/forecast").mock(return_value=httpx.Response(200, json={
        "city": {"name": "Accra", "country": "GH"}, "list": [{
            "dt_txt": "2026-10-23 12:00:00", "weather": [{"description": "Pluie"}],
            "main": {"temp_min": 24, "temp_max": 29}, "pop": 0.8}]}))
    assert "31°C" in await web.get_current_weather("Accra")
    assert "Pluie" in await web.get_weather_forecast("Accra", 2)


@respx.mock
async def test_weather_api_error_is_tool_error():
    respx.get("https://api.openweathermap.org/data/2.5/weather").mock(return_value=httpx.Response(400, json={"error": "No match"}))
    with pytest.raises(ToolError, match="400"):
        await web.get_current_weather("zzzz")


async def test_missing_config_is_explicit(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ToolError, match="TAVILY_API_KEY"):
        await web.web_search("x")


@pytest.mark.parametrize("bad", ["pas-un-email", "a@gmail.c", "a@gmail", "a@@b.com", "a b@c.com"])
async def test_email_validation(bad):
    with pytest.raises(ToolError, match="invalide"):
        await mail.send_email(bad, "s", "b")


@respx.mock
async def test_notion_search_read_create_append():
    page = {"id": "p1", "url": "https://notion.so/p1", "last_edited_time": "2026-10-20T00:00:00Z",
            "properties": {"Name": {"type": "title", "title": [{"plain_text": "Réunion"}]}}}
    respx.post("https://api.notion.com/v1/search").mock(return_value=httpx.Response(200, json={"results": [page]}))
    respx.get("https://api.notion.com/v1/pages/p1").mock(return_value=httpx.Response(200, json=page))
    respx.get("https://api.notion.com/v1/blocks/p1/children").mock(return_value=httpx.Response(200, json={"results": [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Ordre du jour"}]}}]}))
    create = respx.post("https://api.notion.com/v1/pages").mock(return_value=httpx.Response(200, json={"id": "n2", "url": "https://notion.so/n2"}))
    patch = respx.patch("https://api.notion.com/v1/blocks/p1/children").mock(return_value=httpx.Response(200, json={}))
    assert "Réunion" in await notion.search_notion("réu")
    assert "Ordre du jour" in await notion.read_notion_page("p1")
    assert "n2" in await notion.create_notion_page("Titre", "a\nb")
    assert b"parent-1" in create.calls[0].request.content
    await notion.append_to_notion_page("p1", "plus")
    assert patch.called


def test_google_fails_closed_without_test_calendar_and_folder():
    from app.tools import google
    with pytest.raises(ToolError, match="GOOGLE_CALENDAR_ID"):
        google._cal()
    with pytest.raises(ToolError, match="GOOGLE_DRIVE_FOLDER_ID"):
        google._root_folder()


def test_drive_file_must_be_inside_allowed_folder(monkeypatch):
    from app.tools import google
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "root")
    from app.config import get_settings
    get_settings.cache_clear()
    tree = {"inside": ["sub"], "sub": ["root"], "outside": ["other"], "other": []}

    class Drive:
        def files(self): return self
        def get(self, fileId, fields): self.f = fileId; return self
        def execute(self): return {"parents": tree[self.f]}

    assert google._in_allowed_folder(Drive(), "inside") is True
    assert google._in_allowed_folder(Drive(), "outside") is False
