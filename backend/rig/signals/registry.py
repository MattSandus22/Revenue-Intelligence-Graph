"""Signal registry: versioned YAML definitions loaded into memory.

Definitions carry business meaning, parameters, and severity policy; the
detector functions live in engine.py and are looked up by the `detector` key.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


@dataclass(frozen=True)
class SignalDefinition:
    signal: str
    version: int
    category: str
    detector_class: str  # det | stat | ml | llm | hybrid
    detector: str
    params: dict
    severity: dict
    requires_review: bool
    suggested_actions: list[str]

    @property
    def detector_version(self) -> str:
        return f"{self.signal}@v{self.version}"


def load_registry() -> dict[str, SignalDefinition]:
    registry: dict[str, SignalDefinition] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        definition = SignalDefinition(
            signal=raw["signal"],
            version=int(raw["version"]),
            category=raw["category"],
            detector_class=raw["class"],
            detector=raw["detector"],
            params=raw.get("params", {}),
            severity=raw.get("severity", {}),
            requires_review=bool(raw.get("requires_review", False)),
            suggested_actions=list(raw.get("suggested_actions", [])),
        )
        if definition.signal in registry:
            raise ValueError(f"duplicate signal definition: {definition.signal}")
        registry[definition.signal] = definition
    return registry
