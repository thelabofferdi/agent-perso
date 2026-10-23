"""Teste le flux complet de l'API avec un faux LLM : sélection d'outil, approbation, refus, erreurs."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app import main
from app.tools import mail


def llm(tool_name: str, args: dict):
    """Faux LLM : appelle l'outil au 1er tour, puis résume le résultat de l'outil."""
    def fn(messages, info):
        last = messages[-1]
        returns = [p for p in last.parts if isinstance(p, ToolReturnPart)]
        if returns:
            return ModelResponse(parts=[TextPart(f"Résultat: {returns[0].content}")])
        return ModelResponse(parts=[ToolCallPart(tool_name, args)])
    return FunctionModel(fn)


@pytest.fixture
def client(monkeypatch):
    main._sessions.clear(); main._pending.clear(); main._agent = None
    sent = []
    monkeypatch.setattr(mail, "_send", lambda msg: sent.append(msg))
    c = TestClient(main.app); c.sent = sent
    return c


def test_email_requires_approval_then_sends(client):
    with main.agent().override(model=llm("send_email", {"to": "a@b.co", "subject": "Hi", "body": "Salut"})):
        r = client.post("/api/chat", json={"message": "envoie un mail"}).json()
        assert r["type"] == "approval" and r["approvals"][0]["tool"] == "send_email"
        assert client.sent == []  # rien n'est parti avant confirmation
        r2 = client.post("/api/approve", json={"session_id": r["session_id"], "decisions": {r["approvals"][0]["id"]: True}}).json()
    assert r2["type"] == "message" and "E-mail envoyé" in r2["text"]
    assert len(client.sent) == 1 and client.sent[0]["To"] == "a@b.co"


def test_refusal_does_not_send(client):
    with main.agent().override(model=llm("send_email", {"to": "a@b.co", "subject": "Hi", "body": "x"})):
        r = client.post("/api/chat", json={"message": "mail"}).json()
        r2 = client.post("/api/approve", json={"session_id": r["session_id"], "decisions": {r["approvals"][0]["id"]: False}}).json()
    assert client.sent == [] and r2["type"] == "message"


def test_cannot_chat_while_approval_pending(client):
    with main.agent().override(model=llm("send_email", {"to": "a@b.co", "subject": "Hi", "body": "x"})):
        r = client.post("/api/chat", json={"message": "mail"}).json()
        assert client.post("/api/chat", json={"session_id": r["session_id"], "message": "autre"}).status_code == 409


def test_tool_error_reaches_user_as_message(client):
    with main.agent().override(model=llm("get_current_weather", {"city": "Paris"})):
        r = client.post("/api/chat", json={"message": "météo"}).json()
    assert r["type"] == "message" and "get_current_weather" in r["tools_used"] and "ERREUR" in r["text"]


def test_access_code_enforced(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("APP_ACCESS_CODE", "s3cret"); get_settings.cache_clear()
    assert client.post("/api/chat", json={"message": "x"}).status_code == 401
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_served(client):
    assert "Agent IA personnel" in client.get("/").text
