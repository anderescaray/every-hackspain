"""Version-bound configuration: changing any policy requires a registered release."""
import json
from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
from pathlib import Path
from typing import Any

from xray.pulse.contracts import canonical_json

DEFAULT_CONFIG = "pulse_four_pillars_v1_1.json"


@dataclass(frozen=True)
class PulseConfig:
    payload_json: str

    def __post_init__(self) -> None:
        payload = json.loads(self.payload_json)
        canonical = canonical_json(payload)
        object.__setattr__(self, "payload_json", canonical)
        registry = json.loads(files("xray.pulse").joinpath("configs/registry.json").read_text())
        version = payload.get("score_version")
        if version not in registry["score_versions"]:
            raise ValueError(f"Unregistered score_version: {version}")
        if registry["score_versions"][version] != sha256(canonical.encode()).hexdigest():
            raise ValueError("Configuration differs from registered score_version; register a new methodology version")

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    @property
    def config_hash(self) -> str:
        return sha256(self.payload_json.encode()).hexdigest()

    @property
    def score_version(self) -> str:
        return self.to_dict()["score_version"]

    @property
    def classification_version(self) -> str:
        return self.to_dict()["classification_version"]

    @property
    def weights(self) -> dict[str, float]:
        return self.to_dict()["weights"]


def load_config(path: str | Path | None = None) -> PulseConfig:
    text = (Path(path).read_text(encoding="utf-8") if path is not None else
            files("xray.pulse").joinpath("configs", DEFAULT_CONFIG).read_text(encoding="utf-8"))
    return PulseConfig(text)
