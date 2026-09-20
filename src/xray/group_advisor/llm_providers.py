"""Proveedores LLM reales para `Completer` (WP6). Sin llamadas de red en tests.

Dos proveedores; `completer_from_env()` elige según la clave que encuentre:

  - **Anthropic** (SDK oficial `anthropic`) si hay `ANTHROPIC_API_KEY`, si `XRAY_LLM_API_KEY`
    empieza por `sk-ant-`, o si `XRAY_LLM_PROVIDER=anthropic`.
  - **OpenAI-compatible** (chat/completions por HTTP, sin dependencia extra) en el resto de casos.

Variables de entorno:
  ANTHROPIC_API_KEY   — activa el proveedor Anthropic
  XRAY_LLM_API_KEY    (o OPENAI_API_KEY) — clave del proveedor compatible con OpenAI
  XRAY_LLM_PROVIDER   — fuerza "anthropic" u "openai" cuando hay varias claves
  XRAY_LLM_MODEL      — por defecto claude-opus-5 (Anthropic) o gpt-4o-mini (OpenAI)
  XRAY_LLM_BASE_URL   — solo OpenAI-compatible; por defecto https://api.openai.com/v1
  XRAY_LLM_EFFORT     — solo Anthropic: low|medium|high|xhigh|max; por defecto low
  XRAY_LLM_TIMEOUT    — segundos, por defecto 30
  XRAY_LLM_MAX_TOKENS — por defecto 800 (OpenAI) / 4000 (Anthropic, deja sitio al razonamiento)

No se registran la clave ni el prompt completo.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_TOKENS = 800

# Anthropic: el razonamiento adaptativo consume parte de `max_tokens`, así que el techo es más
# alto que en OpenAI aunque la salida sean cuatro viñetas. `effort` bajo porque la tarea es
# redactar con datos ya calculados, no razonar.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_ANTHROPIC_MAX_TOKENS = 4000
DEFAULT_ANTHROPIC_EFFORT = "low"


@dataclass
class OpenAICompatibleCompleter:
    """Cliente chat.completions compatible con OpenAI (y gateways con la misma API)."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT
    max_tokens: int = DEFAULT_MAX_TOKENS

    def complete(self, system: str, user: str) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": int(self.max_tokens),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM network error: {exc.reason}") from None
        data = json.loads(raw)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned empty content")
        return content.strip()


@dataclass
class AnthropicCompleter:
    """Cliente Messages API con el SDK oficial `anthropic`.

    No envía `temperature`: en Claude Opus 5 el parámetro está retirado y devuelve 400. El
    razonamiento adaptativo va activado por defecto en ese modelo y se deja así; `effort` bajo
    basta para redactar a partir de hechos ya calculados.
    """

    api_key: str
    model: str = DEFAULT_ANTHROPIC_MODEL
    timeout: float = DEFAULT_TIMEOUT
    max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS
    effort: str = DEFAULT_ANTHROPIC_EFFORT
    client: object = None  # inyectable en tests; si es None se construye en la primera llamada

    def _ensure_client(self):
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        return self.client

    def complete(self, system: str, user: str) -> str:
        client = self._ensure_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=int(self.max_tokens),
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort},
            )
        except Exception as exc:  # el llamador ya cae a plantilla ante cualquier fallo
            raise RuntimeError(f"LLM Anthropic error: {type(exc).__name__}: {exc}") from None
        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError("LLM Anthropic: la respuesta fue rechazada por seguridad")
        blocks = [b.text for b in getattr(response, "content", []) if getattr(b, "type", None) == "text"]
        text = "\n".join(blocks).strip()
        if not text:
            raise RuntimeError("LLM Anthropic: respuesta sin texto")
        return text


def _load_dotenv(path: Optional[str] = None) -> dict:
    """Carga KEY=VALUE desde `.env` del repo sin dependencia extra. No pisa variables ya exportadas."""
    root = Path(__file__).resolve().parents[2].parent  # src/xray/group_advisor -> repo root
    env_path = Path(path) if path else root / ".env"
    loaded = {}
    if not env_path.is_file():
        return loaded
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = True
    return loaded


def _pick_provider(env, shared_key: str) -> str:
    """"anthropic" u "openai" según la variable explícita, la clave dedicada o el prefijo."""
    forced = (env.get("XRAY_LLM_PROVIDER") or "").strip().lower()
    if forced in ("anthropic", "claude"):
        return "anthropic"
    if forced in ("openai", "openai-compatible"):
        return "openai"
    if (env.get("ANTHROPIC_API_KEY") or "").strip():
        return "anthropic"
    if shared_key.startswith("sk-ant-"):
        return "anthropic"
    return "openai"


def completer_from_env(environ=None):
    """Devuelve un Completer si hay API key; None si no (el producto sigue con plantillas)."""
    if environ is None:
        _load_dotenv()
        env = os.environ
    else:
        env = environ
    shared_key = (env.get("XRAY_LLM_API_KEY") or "").strip()
    timeout = float(env.get("XRAY_LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    model_override = (env.get("XRAY_LLM_MODEL") or "").strip()
    if _pick_provider(env, shared_key) == "anthropic":
        api_key = (env.get("ANTHROPIC_API_KEY") or "").strip() or shared_key
        if not api_key:
            return None
        return AnthropicCompleter(
            api_key=api_key,
            model=model_override or DEFAULT_ANTHROPIC_MODEL,
            timeout=timeout,
            max_tokens=int(env.get("XRAY_LLM_MAX_TOKENS") or DEFAULT_ANTHROPIC_MAX_TOKENS),
            effort=(env.get("XRAY_LLM_EFFORT") or DEFAULT_ANTHROPIC_EFFORT).strip() or DEFAULT_ANTHROPIC_EFFORT,
        )
    api_key = shared_key or (env.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    base_url = (env.get("XRAY_LLM_BASE_URL") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    return OpenAICompatibleCompleter(
        api_key=api_key,
        base_url=base_url,
        model=model_override or DEFAULT_MODEL,
        timeout=timeout,
        max_tokens=int(env.get("XRAY_LLM_MAX_TOKENS") or DEFAULT_MAX_TOKENS),
    )
