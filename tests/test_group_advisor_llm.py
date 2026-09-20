"""WP6: proveedor LLM (sin red) y cableado de completer_from_env."""
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from xray.group_advisor.llm import llm_render
from xray.group_advisor.llm_providers import (
    AnthropicCompleter,
    OpenAICompatibleCompleter,
    completer_from_env,
)
from xray.group_advisor.narrative import render_plan


class FakeCompleter:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.text


def test_completer_from_env_requires_key():
    assert completer_from_env({}) is None
    assert completer_from_env({"OPENAI_API_KEY": "  "}) is None
    c = completer_from_env({"XRAY_LLM_API_KEY": "sk-test", "XRAY_LLM_MODEL": "gpt-test"})
    assert isinstance(c, OpenAICompatibleCompleter)
    assert c.api_key == "sk-test" and c.model == "gpt-test"


def test_openai_compatible_builds_temperature_zero_request(monkeypatch):
    captured = {}

    class DummyResponse:
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "  texto anclado  "}}],
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return DummyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    completer = OpenAICompatibleCompleter(api_key="sk-x", model="gpt-mini", timeout=12, max_tokens=100)
    text = completer.complete("system", "user")
    assert text == "texto anclado"
    assert captured["url"].endswith("/chat/completions")
    assert captured["timeout"] == 12
    assert captured["headers"]["authorization"] == "Bearer sk-x"
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["max_tokens"] == 100
    assert captured["body"]["messages"][0]["content"] == "system"


def test_openai_compatible_http_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise HTTPError(request.full_url, 401, "no", hdrs=None, fp=BytesIO(b'{"error":"no"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="LLM HTTP 401"):
        OpenAICompatibleCompleter(api_key="sk-x").complete("s", "u")


def test_llm_render_still_falls_back_with_provider_style_error(plan_fixture_path=None):
    # Minimal plan-like doc: reuse fixture via narrative tests pattern
    from pathlib import Path
    import json as json_mod
    path = Path(__file__).parent / "fixtures" / "advisor_plan_example.json"
    plan = json_mod.loads(path.read_text(encoding="utf-8"))
    template = render_plan(plan, "markdown")
    result = llm_render(plan, FakeCompleter("El plan sube 999 puntos."))
    assert result.fallback is True and result.text == template


# --- Proveedor Anthropic (SDK oficial, sin red) ------------------------------------------

class _Block:
    def __init__(self, text, type="text"):
        self.text, self.type = text, type


class _Response:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content, self.stop_reason = blocks, stop_reason


class FakeAnthropic:
    """Sustituye a `anthropic.Anthropic`: guarda la petición y devuelve una respuesta fija."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_env_picks_anthropic_by_dedicated_key_prefix_or_override():
    assert isinstance(completer_from_env({"ANTHROPIC_API_KEY": "sk-ant-1"}), AnthropicCompleter)
    # Una clave de Anthropic pegada en la variable compartida también se reconoce.
    assert isinstance(completer_from_env({"XRAY_LLM_API_KEY": "sk-ant-2"}), AnthropicCompleter)
    assert isinstance(completer_from_env({"XRAY_LLM_API_KEY": "sk-proj-3"}), OpenAICompatibleCompleter)
    forced = completer_from_env({"ANTHROPIC_API_KEY": "sk-ant-1", "OPENAI_API_KEY": "sk-4",
                                 "XRAY_LLM_PROVIDER": "openai"})
    assert isinstance(forced, OpenAICompatibleCompleter)
    assert completer_from_env({"ANTHROPIC_API_KEY": "   "}) is None


def test_anthropic_defaults_and_overrides():
    default = completer_from_env({"ANTHROPIC_API_KEY": "sk-ant-1"})
    assert default.model == "claude-opus-5" and default.effort == "low"
    tuned = completer_from_env({"ANTHROPIC_API_KEY": "sk-ant-1", "XRAY_LLM_MODEL": "claude-haiku-4-5",
                                "XRAY_LLM_EFFORT": "medium", "XRAY_LLM_MAX_TOKENS": "1500"})
    assert (tuned.model, tuned.effort, tuned.max_tokens) == ("claude-haiku-4-5", "medium", 1500)


def test_anthropic_request_shape_omits_temperature_and_joins_text_blocks():
    fake = FakeAnthropic(_Response([_Block("Primera viñeta."), _Block("", "thinking"), _Block("Segunda.")]))
    completer = AnthropicCompleter(api_key="sk-ant-1", client=fake)
    assert completer.complete("sistema", "usuario") == "Primera viñeta.\nSegunda."
    sent = fake.calls[0]
    # `temperature` está retirado en Opus 5: enviarlo devuelve 400.
    assert "temperature" not in sent
    assert sent["model"] == "claude-opus-5" and sent["system"] == "sistema"
    assert sent["messages"] == [{"role": "user", "content": "usuario"}]
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] >= 1000  # el razonamiento adaptativo consume parte del techo


def test_anthropic_raises_on_refusal_empty_or_transport_error():
    for response in (_Response([_Block("texto")], stop_reason="refusal"), _Response([])):
        with pytest.raises(RuntimeError):
            AnthropicCompleter(api_key="sk-ant-1", client=FakeAnthropic(response)).complete("s", "u")
    with pytest.raises(RuntimeError):
        AnthropicCompleter(api_key="sk-ant-1", client=FakeAnthropic(error=TimeoutError("red"))).complete("s", "u")
