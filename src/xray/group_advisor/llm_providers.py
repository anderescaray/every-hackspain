"""Proveedores LLM reales para `Completer` (WP6). Sin llamadas de red en tests.

Variables de entorno:
  XRAY_LLM_API_KEY   (o OPENAI_API_KEY) — obligatoria para activar el proveedor
  XRAY_LLM_BASE_URL  — por defecto https://api.openai.com/v1 (compatible OpenAI / gateway)
  XRAY_LLM_MODEL     — por defecto gpt-4o-mini
  XRAY_LLM_TIMEOUT   — segundos, por defecto 30
  XRAY_LLM_MAX_TOKENS — por defecto 800

Temperatura fija 0. No se registran la clave ni el prompt completo.
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


def completer_from_env(environ=None) -> Optional[OpenAICompatibleCompleter]:
    """Devuelve un Completer si hay API key; None si no (el producto sigue con plantillas)."""
    if environ is None:
        _load_dotenv()
        env = os.environ
    else:
        env = environ
    api_key = (env.get("XRAY_LLM_API_KEY") or env.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    base_url = (env.get("XRAY_LLM_BASE_URL") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    model = (env.get("XRAY_LLM_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    timeout = float(env.get("XRAY_LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    max_tokens = int(env.get("XRAY_LLM_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    return OpenAICompatibleCompleter(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        max_tokens=max_tokens,
    )
