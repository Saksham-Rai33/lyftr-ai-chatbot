"""LiteLLM gateway: ordered key pool with failover, built-in response cache,
per-request token usage and the per-request failure-simulation hook."""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import litellm
from litellm.caching.caching import Cache

from .config import Settings

litellm.suppress_debug_info = True  # no "Give Feedback / Get Help" banners in logs
logger = logging.getLogger("app.llm")

SIMULATABLE_STATUSES = {429, 500, 502, 503}


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed (rate limit, quota, 5xx, timeout, ...)."""


@dataclass
class LLMResult:
    reply: str
    resolution_source: str  # "LIVE_INFERENCE" | "LLM_CACHE"
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int
    latency_ms: int

    def metadata(self) -> dict[str, Any]:
        return {
            "resolution_source": self.resolution_source,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "key_id": self.key_id,
            "fallback_attempts": self.fallback_attempts,
        }


def parse_simulation_header(value: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' / '*=429' -> {'key_1': 429, ...}. Bad pairs are ignored."""
    rules: dict[str, int] = {}
    if not value:
        return rules
    for pair in value.split(","):
        name, sep, status = pair.strip().partition("=")
        name, status = name.strip(), status.strip()
        if sep and name and status.isdigit() and int(status) in SIMULATABLE_STATUSES:
            rules[name] = int(status)
    return rules


def _simulated_error(status: int, model: str) -> Exception:
    """Build the exception LiteLLM would raise if the provider returned `status`."""
    msg = f"simulated provider error {status}"
    provider = model.split("/", 1)[0]
    if status == 429:
        return litellm.RateLimitError(message=msg, llm_provider=provider, model=model)
    if status == 503:
        return litellm.ServiceUnavailableError(message=msg, llm_provider=provider, model=model)
    if status == 502 and hasattr(litellm, "BadGatewayError"):
        return litellm.BadGatewayError(message=msg, llm_provider=provider, model=model)
    return litellm.InternalServerError(message=msg, llm_provider=provider, model=model)


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # key_id -> API key / model. Each key may target its own model (and provider).
        self.keys = {f"key_{i}": k for i, k in enumerate(settings.api_keys, start=1)}
        self.models = dict(zip(self.keys, settings.key_models))
        if len(self.keys) < 2:
            logger.warning("Only %d API key configured; failover needs at least 2.", len(self.keys))
        # LiteLLM's built-in in-memory cache. The cache key is derived by LiteLLM from the model
        # and the full message list (system + history + new message); api_key is NOT part of it,
        # so a reply cached via key_2 is still a hit when key_1 is tried first.
        litellm.cache = Cache(type="local", default_in_memory_ttl=settings.cache_ttl_seconds)
        self._warm_up_cache_path()

    @staticmethod
    def _warm_up_cache_path() -> None:
        """First cache hit lazily imports heavy modules; load them at startup instead so the
        first LLM_CACHE response is not slower than a live call."""
        try:
            import litellm.llms.anthropic.messages.native.response_cache  # noqa: F401
        except Exception:  # pragma: no cover - purely an optimisation
            pass

    @property
    def cache_enabled(self) -> bool:
        return litellm.cache is not None

    async def complete(
        self, messages: list[dict[str, str]], simulate: dict[str, int] | None = None
    ) -> LLMResult:
        simulate = simulate or {}
        started = time.perf_counter()
        failures = 0
        for key_id, api_key in self.keys.items():
            model = self.models[key_id]
            status = simulate.get(key_id) or simulate.get("*")
            try:
                if status:
                    raise _simulated_error(status, model)
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    api_key=api_key,
                    api_base=self.settings.llm_api_base,
                    timeout=self.settings.llm_timeout_seconds,
                    num_retries=0,  # failover across keys is ours; no hidden same-key retries
                    # A simulation must exercise the real key loop, so it never reads the cache.
                    caching=not simulate,
                )
                reply = (response.choices[0].message.content or "").strip()
                if not reply:
                    raise ValueError("provider returned an empty reply")
            except Exception as exc:  # any provider failure -> next key; never leak to the user
                failures += 1
                logger.warning(
                    "%s failed (%s: %s); %s",
                    key_id,
                    type(exc).__name__,
                    getattr(exc, "status_code", "n/a"),
                    "trying next key" if failures < len(self.keys) else "no keys left",
                )
                continue

            latency_ms = int((time.perf_counter() - started) * 1000)
            hit = bool(getattr(response, "_hidden_params", {}).get("cache_hit"))
            if not hit:
                # LiteLLM writes the cache entry in a background task; give it a moment so an
                # immediate repeat of this prompt is already a hit. Excluded from latency_ms.
                await asyncio.sleep(0.05)
            input_tokens, output_tokens = self._usage(model, response, messages, reply)
            return LLMResult(
                reply=reply,
                resolution_source="LLM_CACHE" if hit else "LIVE_INFERENCE",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                key_id=None if hit else key_id,
                fallback_attempts=0 if hit else failures,
                latency_ms=latency_ms,
            )
        raise AllProvidersUnavailable()

    @staticmethod
    def _usage(model: str, response: Any, messages: list[dict[str, str]], reply: str) -> tuple[int, int]:
        """Tokens for THIS request only. Falls back to a local estimate if the provider omits usage."""
        usage = getattr(response, "usage", None)
        inp = getattr(usage, "prompt_tokens", None)
        out = getattr(usage, "completion_tokens", None)
        if inp is None:
            inp = litellm.token_counter(model=model, messages=messages)
        if out is None:
            out = litellm.token_counter(model=model, text=reply)
        return int(inp), int(out)
