"""API FastAPI + interface de chat. Sessions en mémoire ; approbations gérées côté serveur."""

import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pydantic_ai import DeferredToolRequests, DeferredToolResults, ModelRetry, ToolDenied
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from app.agent import build_agent
from app.config import get_settings

STATIC = Path(__file__).parent / "static"
MAX_SESSIONS = 200

app = FastAPI(title="Agent IA personnel")
_agent = None
_sessions: dict[str, list[ModelMessage]] = {}
_pending: dict[str, DeferredToolRequests] = {}


def agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def check_access(x_access_code: str | None = Header(default=None)) -> None:
    code = get_settings().access_code
    if code and not secrets.compare_digest(x_access_code or "", code):
        raise HTTPException(401, "Code d'accès invalide.")


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)


class ApproveIn(BaseModel):
    session_id: str
    decisions: dict[str, bool]


def _tools_used(messages: list[ModelMessage]) -> list[str]:
    return [p.tool_name for m in messages if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, ToolCallPart)]


async def _run(sid: str, prompt: str | None, results: DeferredToolResults | None = None) -> dict:
    history = _sessions.get(sid, [])
    try:
        res = await agent().run(prompt, message_history=history, deferred_tool_results=results)
    except ModelHTTPError as exc:
        messages = {
            401: "Clé API LLM invalide.",
            402: "Crédit RodiumAI insuffisant : rechargez le portefeuille.",
            429: "Trop de requêtes vers le LLM, réessayez dans un instant.",
        }
        status = 401 if exc.status_code == 401 else 502
        detail = messages.get(exc.status_code, f"Le fournisseur LLM a répondu {exc.status_code}.")
        return JSONResponse({"error": detail}, status_code=status)
    except (UnexpectedModelBehavior, ModelRetry):
        return JSONResponse({"error": "L'agent n'a pas pu terminer la tâche, reformulez la demande."}, status_code=502)
    new = res.new_messages()
    _sessions[sid] = res.all_messages()
    used = _tools_used(new)
    if isinstance(res.output, DeferredToolRequests):
        _pending[sid] = res.output
        calls = {c.tool_call_id: c for c in res.output.approvals}
        return {"type": "approval", "session_id": sid, "tools_used": used, "approvals": [
            {"id": i, "tool": c.tool_name, "args": c.args_as_dict()} for i, c in calls.items()
        ]}
    _pending.pop(sid, None)
    return {"type": "message", "session_id": sid, "text": res.output, "tools_used": used}


@app.post("/api/chat", dependencies=[Depends(check_access)])
async def chat(body: ChatIn):
    if len(_sessions) >= MAX_SESSIONS:
        _sessions.pop(next(iter(_sessions)))
    sid = body.session_id or uuid.uuid4().hex
    if sid in _pending:
        raise HTTPException(409, "Une action attend votre confirmation.")
    return await _run(sid, body.message)


@app.post("/api/approve", dependencies=[Depends(check_access)])
async def approve(body: ApproveIn):
    pending = _pending.get(body.session_id)
    if pending is None:
        raise HTTPException(404, "Aucune action en attente.")
    results = DeferredToolResults()
    for call in pending.approvals:
        ok = body.decisions.get(call.tool_call_id, False)
        results.approvals[call.tool_call_id] = True if ok else ToolDenied("L'utilisateur a refusé cette action.")
    return await _run(body.session_id, None, results)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    return {"access_code_required": bool(get_settings().access_code)}


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
