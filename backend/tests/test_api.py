import pytest

from tests.conftest import GOOD1, GOOD2


def chat(client, session, message, headers=None, **extra):
    return client.post("/chat", json={"session_id": session, "message": message, **extra}, headers=headers or {})


# ---- /health -------------------------------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_health_503_without_keys(make_client):
    r = make_client(keys="").get("/health")
    assert r.status_code == 503


# ---- validation (422) ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "s", "message": ""},
        {"session_id": "s", "message": "   \n\t "},
        {"session_id": "s", "message": "x" * 4001},
        {"session_id": "s"},
        {"message": "hi"},
        {"session_id": "", "message": "hi"},
        {"session_id": "s" * 129, "message": "hi"},
        {},
    ],
)
def test_422_validation(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()
    assert client.get("/sessions/s/messages").status_code == 404  # nothing stored


def test_422_malformed_json(client):
    r = client.post("/chat", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_message_boundaries_ok(client):
    assert chat(client, "b1", "x" * 4000).status_code == 200
    assert chat(client, "b2", "  padded  ").status_code == 200
    assert client.get("/sessions/b2/messages").json()["messages"][0]["content"] == "padded"
    assert chat(client, "s" * 128, "hi").status_code == 200


def test_no_html_or_traceback_on_unknown_route(client):
    r = client.get("/nope")
    assert r.status_code == 404 and "detail" in r.json()


# ---- contract shape, tokens ----------------------------------------------------------------
def test_chat_contract_shape(client):
    r = chat(client, "s1", "What is the capital of France?")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1" and body["reply"]
    m = body["metadata"]
    assert m["resolution_source"] == "LIVE_INFERENCE"
    assert m["model"] == "openai/fake-model"
    assert isinstance(m["latency_ms"], int) and m["latency_ms"] > 0
    assert m["input_tokens"] > 0 and m["output_tokens"] == 7
    assert m["key_id"] == "key_1" and m["fallback_attempts"] == 0


def test_tokens_are_per_request_not_cumulative(client):
    a = chat(client, "t1", "hello there").json()["metadata"]
    b = chat(client, "t2", "hello there").json()["metadata"]  # identical first message, new session
    assert a["input_tokens"] == b["input_tokens"]
    # follow-up in t1 carries history, so prompt tokens grow, but output stays per-request
    c = chat(client, "t1", "and another thing").json()["metadata"]
    assert c["input_tokens"] > a["input_tokens"] and c["output_tokens"] == 7


# ---- caching -------------------------------------------------------------------------------
def test_cache_hit_in_new_session(client):
    first = chat(client, "c1", "cache me please").json()
    second = chat(client, "c2", "cache me please").json()  # same first message, different session
    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert second["metadata"]["resolution_source"] == "LLM_CACHE"
    assert second["reply"] == first["reply"]
    assert second["metadata"]["key_id"] is None and second["metadata"]["fallback_attempts"] == 0
    assert second["metadata"]["input_tokens"] == first["metadata"]["input_tokens"]
    assert second["metadata"]["output_tokens"] == first["metadata"]["output_tokens"]
    assert second["metadata"]["latency_ms"] < first["metadata"]["latency_ms"]


def test_cache_hit_when_repeated_immediately(client):
    chat(client, "i1", "immediate repeat")
    assert chat(client, "i2", "immediate repeat").json()["metadata"]["resolution_source"] == "LLM_CACHE"


def test_different_message_never_cached(client, fake_provider):
    chat(client, "d1", "message one")
    r = chat(client, "d2", "message two").json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r["reply"].endswith("message two")


def test_different_history_is_a_different_cache_key(client):
    chat(client, "h1", "hello")
    chat(client, "h1", "follow up")
    # "follow up" as the FIRST message of a new session has different context -> must be live
    assert chat(client, "h2", "follow up").json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_different_system_prompt_is_a_different_cache_key(client):
    chat(client, "p1", "same text", system_prompt="You are a pirate.")
    other = chat(client, "p2", "same text", system_prompt="You are a poet.").json()
    same = chat(client, "p3", "same text", system_prompt="You are a pirate.").json()
    assert other["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert same["metadata"]["resolution_source"] == "LLM_CACHE"


# ---- multi-turn + history endpoint ---------------------------------------------------------
def test_multi_turn_context_sent_to_llm(client, fake_provider):
    chat(client, "m1", "My name is Sam")
    chat(client, "m1", "What is my name?")
    sent = fake_provider.requests[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "My name is Sam" and sent[3]["content"] == "What is my name?"


def test_sessions_are_isolated(client, fake_provider):
    chat(client, "iso-a", "secret alpha")
    chat(client, "iso-b", "something else")
    sent = fake_provider.requests[-1]["messages"]
    assert all("secret alpha" not in m["content"] for m in sent)
    assert len(client.get("/sessions/iso-a/messages").json()["messages"]) == 2


def test_history_endpoint_shape(client):
    chat(client, "hist", "first")
    chat(client, "hist", "second")
    body = client.get("/sessions/hist/messages").json()
    assert body["session_id"] == "hist"
    msgs = body["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "first" and "metadata" not in msgs[0]
    meta = msgs[1]["metadata"]
    assert {"resolution_source", "input_tokens", "output_tokens"} <= meta.keys()
    assert all(m["role"] != "system" for m in msgs)


def test_history_404(client):
    r = client.get("/sessions/unknown/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}


def test_history_survives_restart(make_client):
    c1 = make_client(db_name="persist.db")
    chat(c1, "keep", "remember this")
    c2 = make_client(db_name="persist.db")  # new app instance, same DB file
    assert len(c2.get("/sessions/keep/messages").json()["messages"]) == 2


def test_system_prompt_is_remembered_for_session(client, fake_provider):
    chat(client, "sp", "hi", system_prompt="Talk like a pirate.")
    chat(client, "sp", "again")  # no system_prompt this time
    assert fake_provider.requests[-1]["messages"][0]["content"] == "Talk like a pirate."


# ---- failover ------------------------------------------------------------------------------
@pytest.mark.parametrize("header", ["key_1=429", "key_1=500", "key_1=502", "key_1=503"])
def test_simulated_failover_to_key_2(client, header):
    r = chat(client, "f-" + header, "failover please", headers={"X-Simulate-Failure": header})
    assert r.status_code == 200
    m = r.json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1
    assert m["resolution_source"] == "LIVE_INFERENCE"
    assert not r.json()["reply"].lower().startswith("error")


def test_simulated_failover_bypasses_cache(client):
    chat(client, "fc1", "warm cache")
    chat(client, "fc2", "warm cache")  # now definitely cached
    r = chat(client, "fc3", "warm cache", headers={"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_all_keys_failing_returns_503_and_stores_nothing(client):
    r = chat(client, "all-fail", "hello", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}
    assert client.get("/sessions/all-fail/messages").status_code == 404


def test_all_keys_failing_even_when_prompt_is_cached(client):
    chat(client, "ac1", "cached prompt")
    chat(client, "ac2", "cached prompt")
    r = chat(client, "ac3", "cached prompt", headers={"X-Simulate-Failure": "*=503"})
    assert r.status_code == 503


def test_503_does_not_pollute_existing_history(client):
    chat(client, "pol", "good message")
    assert chat(client, "pol", "bad message", headers={"X-Simulate-Failure": "*=500"}).status_code == 503
    assert len(client.get("/sessions/pol/messages").json()["messages"]) == 2


def test_both_keys_listed_explicitly(client):
    r = chat(client, "both", "x", headers={"X-Simulate-Failure": "key_1=429,key_2=500"})
    assert r.status_code == 503


def test_simulation_is_per_request_only(client):
    chat(client, "per1", "one", headers={"X-Simulate-Failure": "key_1=429"})
    m = chat(client, "per2", "two").json()["metadata"]
    assert m["key_id"] == "key_1" and m["fallback_attempts"] == 0


def test_header_ignored_when_flag_off(make_client):
    c = make_client(simulation=False)
    r = chat(c, "off", "hello", headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_1"


@pytest.mark.parametrize("header", ["garbage", "key_1=418", "key_1=", "=429", "key_1=abc"])
def test_malformed_simulation_header_is_ignored(client, header):
    r = chat(client, "bad-" + header, "hi", headers={"X-Simulate-Failure": header})
    assert r.status_code == 200 and r.json()["metadata"]["fallback_attempts"] == 0


# ---- real provider failures (not simulated) ------------------------------------------------
def test_real_429_fails_over(make_client):
    c = make_client(keys=f"sk-RATELIMITED,{GOOD2}")
    m = chat(c, "real429", "hello").json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1


def test_real_5xx_fails_over(make_client):
    c = make_client(keys=f"sk-BROKEN,{GOOD2}")
    m = chat(c, "real500", "hello").json()["metadata"]
    assert m["key_id"] == "key_2" and m["fallback_attempts"] == 1


def test_all_real_failures_give_clean_503(make_client):
    c = make_client(keys="sk-RATELIMITED,sk-BROKEN")
    r = chat(c, "realall", "hello")
    assert r.status_code == 503 and r.json() == {"detail": "all providers unavailable"}


def test_each_key_can_use_its_own_model(make_client):
    c = make_client(models="openai/model-a,openai/model-b")
    first = chat(c, "pm1", "hello").json()["metadata"]
    assert (first["key_id"], first["model"]) == ("key_1", "openai/model-a")
    over = chat(c, "pm2", "other", headers={"X-Simulate-Failure": "key_1=429"}).json()["metadata"]
    assert (over["key_id"], over["model"]) == ("key_2", "openai/model-b")


def test_key_values_never_leak(client):
    r = chat(client, "leak", "hello", headers={"X-Simulate-Failure": "key_1=429"})
    assert GOOD1 not in r.text and GOOD2 not in r.text
    assert GOOD1 not in client.get("/sessions/leak/messages").text


# ---- CORS ----------------------------------------------------------------------------------
def test_cors_preflight_allows_simulate_header(client):
    r = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-simulate-failure" in r.headers["access-control-allow-headers"].lower()
