"""Test harness: a tiny fake OpenAI-compatible server so LiteLLM's *real* cache and
failure handling are exercised (litellm's mock_response bypasses the cache)."""
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

GOOD1, GOOD2 = "sk-key-one-GOOD", "sk-key-two-GOOD"


class FakeProvider:
    def __init__(self) -> None:
        self.requests: list[dict] = []  # {"key": ..., "messages": [...]}
        self.delay = 0.25  # makes a live call measurably slower than a cache hit
        self.base_url = ""

    def reset(self) -> None:
        self.requests.clear()


def _build_fake(state: FakeProvider) -> FastAPI:
    api = FastAPI()

    @api.post("/v1/chat/completions")
    async def completions(req: Request):
        body = await req.json()
        key = req.headers.get("authorization", "").removeprefix("Bearer ")
        state.requests.append({"key": key, "messages": body["messages"]})
        if key.endswith("RATELIMITED"):
            return JSONResponse({"error": {"message": "quota exceeded", "type": "rate_limit"}}, status_code=429)
        if key.endswith("BROKEN"):
            return JSONResponse({"error": {"message": "boom", "type": "server_error"}}, status_code=500)
        time.sleep(state.delay)
        msgs = body["messages"]
        last = msgs[-1]["content"]
        prompt_tokens = sum(len(m["content"]) for m in msgs) // 4 + 3
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": f"reply#{len(msgs)}: {last}"},
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 7,
                "total_tokens": prompt_tokens + 7,
            },
        }

    return api


@pytest.fixture(scope="session")
def fake_provider():
    state = FakeProvider()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(_build_fake(state), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    state.base_url = f"http://127.0.0.1:{port}/v1"
    yield state
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def make_client(tmp_path, fake_provider):
    """Factory -> TestClient (lifespan running) against a fresh DB and a fresh LiteLLM cache."""
    clients: list[TestClient] = []

    def _make(
        keys: str = f"{GOOD1},{GOOD2}", simulation: bool = True, db_name: str = "app.db", models: str = ""
    ) -> TestClient:
        fake_provider.reset()
        settings = Settings(
            _env_file=None,
            LLM_API_KEYS=keys,
            LLM_MODEL="openai/fake-model",
            LLM_MODELS=models,
            LLM_API_BASE=fake_provider.base_url,
            DATABASE_URL=f"sqlite:///{(tmp_path / db_name).as_posix()}",
            ALLOWED_ORIGINS="http://localhost:3000",
            ENABLE_FAILURE_SIMULATION=simulation,
        )
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()
