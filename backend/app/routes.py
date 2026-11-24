"""The three contract endpoints: /health, /chat, /sessions/{id}/messages."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from . import db
from .llm import parse_simulation_header
from .schemas import ChatRequest, ChatResponse, HistoryResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    state = request.app.state
    db_ok = await asyncio.to_thread(db.ping, state.settings.database_path)
    keys = len(state.llm.keys)
    if not db_ok or keys == 0:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "keys_configured": keys,
                     "cache_enabled": state.llm.cache_enabled, "detail": "database or key pool not ready"},
        )
    return {"status": "ok", "keys_configured": keys, "cache_enabled": state.llm.cache_enabled}


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    state = request.app.state
    settings, llm, path = state.settings, state.llm, state.settings.database_path

    simulate: dict[str, int] = {}
    if settings.enable_failure_simulation:
        simulate = parse_simulation_header(request.headers.get("x-simulate-failure"))

    # One in-flight request per session so concurrent sends never interleave history.
    async with state.session_locks.get(body.session_id):
        history = await asyncio.to_thread(db.get_history, path, body.session_id)
        stored_prompt = await asyncio.to_thread(db.get_session_prompt, path, body.session_id)
        system_prompt = body.system_prompt or stored_prompt or settings.default_system_prompt

        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": body.message})

        # Raises AllProvidersUnavailable -> 503 (handled in main.py). Nothing is persisted then.
        result = await llm.complete(messages, simulate)
        metadata = result.metadata()

        await asyncio.to_thread(
            db.save_exchange, path, body.session_id, body.message, result.reply, metadata, body.system_prompt
        )

    return {"session_id": body.session_id, "reply": result.reply, "metadata": metadata}


@router.get("/sessions/{session_id}/messages", response_model=HistoryResponse, response_model_exclude_none=True)
async def session_messages(session_id: str, request: Request):
    messages = await asyncio.to_thread(db.get_history, request.app.state.settings.database_path, session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": messages}
