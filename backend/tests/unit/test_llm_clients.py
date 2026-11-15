"""Offline unit tests for async httpx LLM clients, ModelRouter, FakeLLMClient, and factory."""

import ast
import json
import tomllib
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from commerce_ai.adapters.llm import (
    FakeLLMClient,
    GeminiLLMClient,
    ModelRouterLLMClient,
    OpenAICompatibleLLMClient,
    create_llm_client,
)
from commerce_ai.config.settings import AppSettings
from commerce_ai.domain.errors import LLMProviderError
from commerce_ai.domain.models import LLMMessage, LLMRequest, LLMResponse
from commerce_ai.domain.ports import LLMClient


def _sample_request(*, json_mode: bool = True) -> LLMRequest:
    return LLMRequest(
        messages=(
            LLMMessage(role="system", content="Extract shopping intent JSON."),
            LLMMessage(role="user", content="سماعة أنكر في مصر"),
            LLMMessage(role="assistant", content='{"action":"clarify"}'),
            LLMMessage(role="user", content="تحت ٢٠٠٠ جنيه"),
        ),
        max_tokens=300,
        temperature=0.0,
        json_mode=json_mode,
        task_name="intent_extraction",
    )


async def test_gemini_client_request_and_response() -> None:
    """T1.6 — GeminiLLMClient uses header-only auth, maps payload, and parses LLMResponse."""
    captured: list[httpx.Request] = []
    secret = "gem-secret-xyz-123"

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"action":"search","query":"Anker earbuds"}'}]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 42,
                    "candidatesTokenCount": 15,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GeminiLLMClient(
            api_key=SecretStr(secret),
            model="gemini/gemini-2.5-flash",
            timeout_seconds=5.0,
            http_client=http_client,
        )
        assert isinstance(client, LLMClient)
        response = await client.complete(_sample_request(json_mode=True))

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert str(req.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert "key=" not in str(req.url)
    assert secret not in str(req.url)
    assert req.headers["x-goog-api-key"] == secret

    body = json.loads(req.content.decode("utf-8"))
    assert body["systemInstruction"] == {"parts": [{"text": "Extract shopping intent JSON."}]}
    assert [item["role"] for item in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"]["maxOutputTokens"] == 300
    assert body["generationConfig"]["temperature"] == 0.0
    assert body["generationConfig"]["responseMimeType"] == "application/json"

    assert response.provider == "gemini"
    assert response.model == "gemini-2.5-flash"
    assert response.content == '{"action":"search","query":"Anker earbuds"}'
    assert response.input_tokens == 42
    assert response.output_tokens == 15
    assert response.used_fallback_model is False


async def test_openai_compatible_client_request_and_response() -> None:
    """T1.7 — OpenAICompatibleLLMClient routes Groq, OpenAI, and custom base URLs."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "model": "returned-model-id",
                "choices": [{"message": {"content": '{"action":"search","query":"laptop"}'}}],
                "usage": {"prompt_tokens": 31, "completion_tokens": 12},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        groq = OpenAICompatibleLLMClient(
            api_key=SecretStr("groq-secret-1"),
            model="groq/llama-3.3-70b-versatile",
            http_client=http_client,
        )
        openai = OpenAICompatibleLLMClient(
            api_key=SecretStr("openai-secret-2"),
            model="openai/gpt-4o-mini",
            http_client=http_client,
        )
        custom = OpenAICompatibleLLMClient(
            api_key=SecretStr("local-token"),
            model="meta-llama/Llama-3.3-70B-Instruct",
            provider="vllm",
            base_url="http://localhost:8080/v1/",
            http_client=http_client,
        )

        res_groq = await groq.complete(_sample_request(json_mode=True))
        res_openai = await openai.complete(_sample_request(json_mode=True))
        res_custom = await custom.complete(_sample_request(json_mode=False))

    assert len(captured) == 3
    assert str(captured[0].url) == "https://api.groq.com/openai/v1/chat/completions"
    assert captured[0].headers["authorization"] == "Bearer groq-secret-1"
    groq_payload = json.loads(captured[0].content.decode("utf-8"))
    assert groq_payload["model"] == "llama-3.3-70b-versatile"
    assert groq_payload["response_format"] == {"type": "json_object"}

    assert str(captured[1].url) == "https://api.openai.com/v1/chat/completions"
    assert captured[1].headers["authorization"] == "Bearer openai-secret-2"
    openai_payload = json.loads(captured[1].content.decode("utf-8"))
    assert openai_payload["model"] == "gpt-4o-mini"

    assert str(captured[2].url) == "http://localhost:8080/v1/chat/completions"
    custom_payload = json.loads(captured[2].content.decode("utf-8"))
    assert custom_payload["model"] == "meta-llama/Llama-3.3-70B-Instruct"
    assert "response_format" not in custom_payload

    assert res_groq.provider == "groq"
    assert res_openai.provider == "openai"
    assert res_custom.provider == "vllm"
    assert res_groq.input_tokens == 31
    assert res_groq.output_tokens == 12


async def test_model_router_primary_and_single_failover() -> None:
    """T1.8 — ModelRouterLLMClient skips fallback on success and fails over once on error."""
    primary_ok = FakeLLMClient(responses=['{"action":"search"}'], provider="gemini", model="g1")
    fallback_unused = FakeLLMClient(responses=['{"action":"clarify"}'], provider="groq", model="f1")
    router_ok = ModelRouterLLMClient(primary=primary_ok, fallback=fallback_unused)

    req = _sample_request()
    resp_ok = await router_ok.complete(req)
    assert resp_ok.content == '{"action":"search"}'
    assert resp_ok.used_fallback_model is False
    assert primary_ok.call_count == 1
    assert fallback_unused.call_count == 0

    primary_err = FakeLLMClient(
        responses=[LLMProviderError(provider="gemini", retriable=True, reason="429")],
        provider="gemini",
        model="g1",
    )
    fallback_used = FakeLLMClient(
        responses=['{"action":"search","query":"fallback"}'],
        provider="groq",
        model="llama-3.3-70b-versatile",
    )
    router_failover = ModelRouterLLMClient(primary=primary_err, fallback=fallback_used)

    resp_fb = await router_failover.complete(req)
    assert resp_fb.content == '{"action":"search","query":"fallback"}'
    assert resp_fb.provider == "groq"
    assert resp_fb.used_fallback_model is True
    assert primary_err.call_count == 1
    assert fallback_used.call_count == 1
    await router_failover.aclose()


async def test_fake_llm_client_records_requests() -> None:
    """T1.9 — FakeLLMClient supports queues, handlers, defaults, and request inspection."""
    custom_resp = LLMResponse(
        content="custom-object",
        provider="fake-custom",
        model="fake-2",
        input_tokens=5,
        output_tokens=2,
    )
    fake = FakeLLMClient(
        responses=[
            '{"action":"search"}',
            custom_resp,
            LLMProviderError(provider="fake", retriable=True, reason="simulated"),
        ],
        handler=lambda req: f"handled:{req.task_name}",
    )

    req1 = _sample_request(json_mode=True)
    req2 = _sample_request(json_mode=False)
    r1 = await fake.complete(req1)
    r2 = await fake.complete(req2)
    assert r1.content == '{"action":"search"}'
    assert r2 == custom_resp

    with pytest.raises(LLMProviderError):
        await fake.complete(req1)

    r4 = await fake.complete(req2)
    assert r4.content == "handled:intent_extraction"
    assert fake.call_count == 4
    assert fake.requests == [req1, req2, req1, req2]

    default_fake = FakeLLMClient()
    d_json = await default_fake.complete(_sample_request(json_mode=True))
    d_text = await default_fake.complete(_sample_request(json_mode=False))
    assert json.loads(d_json.content)["action"] == "search"
    assert len(d_text.content) > 0
    await default_fake.aclose()


def test_create_llm_client_modes() -> None:
    """T1.10 — create_llm_client honors fake, auto, and live configuration modes."""
    fake_client = create_llm_client(
        AppSettings(_env_file=None, llm_mode="fake", gemini_api_key=SecretStr("unused"))
    )
    assert isinstance(fake_client, FakeLLMClient)

    auto_no_keys = create_llm_client(AppSettings(_env_file=None, llm_mode="auto"))
    assert auto_no_keys is None

    auto_both = create_llm_client(
        AppSettings(
            _env_file=None,
            llm_mode="auto",
            gemini_api_key=SecretStr("gem-key"),
            groq_api_key=SecretStr("groq-key"),
        )
    )
    assert isinstance(auto_both, ModelRouterLLMClient)
    assert isinstance(auto_both.primary, GeminiLLMClient)
    assert isinstance(auto_both.fallback, OpenAICompatibleLLMClient)

    auto_fallback_only = create_llm_client(
        AppSettings(
            _env_file=None,
            llm_mode="auto",
            groq_api_key=SecretStr("groq-only-key"),
        )
    )
    assert isinstance(auto_fallback_only, ModelRouterLLMClient)
    assert isinstance(auto_fallback_only.primary, OpenAICompatibleLLMClient)
    assert auto_fallback_only.fallback is None

    live_client = create_llm_client(
        AppSettings(
            _env_file=None,
            llm_mode="live",
            openai_api_key=SecretStr("oa-key"),
            llm_primary_model="openai/gpt-4o-mini",
            llm_fallback_model=None,
        )
    )
    assert isinstance(live_client, ModelRouterLLMClient)
    assert isinstance(live_client.primary, OpenAICompatibleLLMClient)
    assert live_client.fallback is None


async def test_llm_clients_error_classification_and_secret_redaction() -> None:
    """T3.5 — LLM HTTP/transport/payload errors map to LLMProviderError with redacted secrets."""
    gem_secret = "gem-super-secret-token"
    groq_secret = "groq-super-secret-token"

    scenarios: list[tuple[object, bool]] = [
        (httpx.ReadTimeout(f"timeout with {gem_secret}"), True),
        (httpx.ConnectError(f"connect failed with {gem_secret}"), True),
        (httpx.Response(429, text=f"rate limit {gem_secret}"), True),
        (httpx.Response(503, text="service unavailable"), True),
        (httpx.Response(401, text=f"invalid key {gem_secret}"), False),
        (httpx.Response(400, text="bad request"), False),
        (httpx.Response(200, text="not-json"), False),
        (httpx.Response(200, json={"unexpected": "shape"}), False),
        (
            httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "   "}]}}]}),
            False,
        ),
    ]

    for outcome, expected_retriable in scenarios:

        def gem_handler(request: httpx.Request, out: object = outcome) -> httpx.Response:
            if isinstance(out, Exception):
                raise out
            assert isinstance(out, httpx.Response)
            return out

        async with httpx.AsyncClient(transport=httpx.MockTransport(gem_handler)) as hc:
            client = GeminiLLMClient(api_key=SecretStr(gem_secret), http_client=hc)
            with pytest.raises(LLMProviderError) as exc_info:
                await client.complete(_sample_request())
            assert exc_info.value.provider == "gemini"
            assert exc_info.value.retriable is expected_retriable
            assert gem_secret not in str(exc_info.value)

    oai_scenarios: list[tuple[object, bool]] = [
        (httpx.ReadTimeout(f"timeout with {groq_secret}"), True),
        (httpx.ConnectError(f"connect failed with {groq_secret}"), True),
        (httpx.Response(429, text="rate limit"), True),
        (httpx.Response(502, text="bad gateway"), True),
        (httpx.Response(403, text=f"forbidden {groq_secret}"), False),
        (httpx.Response(200, text="{bad-json"), False),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), False),
    ]

    for outcome, expected_retriable in oai_scenarios:

        def oai_handler(request: httpx.Request, out: object = outcome) -> httpx.Response:
            if isinstance(out, Exception):
                raise out
            assert isinstance(out, httpx.Response)
            return out

        async with httpx.AsyncClient(transport=httpx.MockTransport(oai_handler)) as hc:
            client = OpenAICompatibleLLMClient(
                api_key=SecretStr(groq_secret),
                model="groq/llama-3.3-70b-versatile",
                http_client=hc,
            )
            with pytest.raises(LLMProviderError) as exc_info:
                await client.complete(_sample_request())
            assert exc_info.value.provider == "groq"
            assert exc_info.value.retriable is expected_retriable
            assert groq_secret not in str(exc_info.value)


async def test_model_router_exhaustion_raises_provider_error() -> None:
    """T3.6 — ModelRouterLLMClient propagates LLMProviderError when fallback missing or fails."""
    primary_fail = FakeLLMClient(
        responses=[LLMProviderError(provider="gemini", retriable=True, reason="primary down")]
    )
    no_fb_router = ModelRouterLLMClient(primary=primary_fail, fallback=None)
    with pytest.raises(LLMProviderError, match="primary down"):
        await no_fb_router.complete(_sample_request())

    primary_fail_2 = FakeLLMClient(
        responses=[LLMProviderError(provider="gemini", retriable=True, reason="primary down")]
    )
    fallback_fail = FakeLLMClient(
        responses=[LLMProviderError(provider="groq", retriable=False, reason="fallback down")]
    )
    exhausted_router = ModelRouterLLMClient(primary=primary_fail_2, fallback=fallback_fail)
    with pytest.raises(LLMProviderError, match="fallback down"):
        await exhausted_router.complete(_sample_request())
    assert primary_fail_2.call_count == 1
    assert fallback_fail.call_count == 1


def test_create_llm_client_live_missing_key_raises() -> None:
    """T3.7 — create_llm_client rejects missing keys or unsupported providers in live mode."""
    with pytest.raises(LLMProviderError) as missing_exc:
        create_llm_client(AppSettings(_env_file=None, llm_mode="live"))
    assert missing_exc.value.provider == "llm"
    assert missing_exc.value.retriable is False

    with pytest.raises(LLMProviderError) as bad_provider_exc:
        create_llm_client(
            AppSettings(
                _env_file=None,
                llm_mode="live",
                llm_primary_model="anthropic/claude-3-5-haiku",
                llm_fallback_model=None,
            )
        )
    assert bad_provider_exc.value.provider == "llm"
    assert bad_provider_exc.value.retriable is False

    with pytest.raises(LLMProviderError) as bad_format_exc:
        create_llm_client(
            AppSettings(
                _env_file=None,
                llm_mode="live",
                llm_primary_model="gemini-2.5-flash",
                llm_fallback_model=None,
            )
        )
    assert bad_format_exc.value.provider == "llm"
    assert bad_format_exc.value.retriable is False


def test_live_smoke_marker_registered_and_deselected(
    request: pytest.FixtureRequest,
) -> None:
    """T1.14 — Live smoke test is marked @pytest.mark.live and deselected by default."""
    backend_root = Path(__file__).resolve().parents[2]
    smoke_path = backend_root / "tests" / "integration" / "test_live_llm_smoke.py"
    assert smoke_path.is_file()

    tree = ast.parse(smoke_path.read_text(encoding="utf-8"))
    live_decorated = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(dec, ast.Attribute)
            and dec.attr == "live"
            and isinstance(dec.value, ast.Attribute)
            and dec.value.attr == "mark"
            for dec in node.decorator_list
        )
    ]
    assert "test_live_llm_intent_extraction_smoke" in live_decorated

    pyproject_data = tomllib.loads((backend_root / "pyproject.toml").read_text(encoding="utf-8"))
    ini_opts = pyproject_data["tool"]["pytest"]["ini_options"]
    assert ini_opts["addopts"] == ["-m", "not live"]
    assert any(str(marker).startswith("live:") for marker in ini_opts["markers"])

    registered_markers = "\n".join(str(marker) for marker in request.config.getini("markers"))
    assert "live:" in registered_markers
    assert request.config.option.markexpr == "not live"
