from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheMeta:
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class State:
    last_hash_arbys: str | None = None
    last_hash_incursions: str | None = None
    last_hash_invasions: str | None = None
    last_hash_earth_cycle: str | None = None
    last_hash_open_world_cycles: str | None = None
    message_id_arbys: int | None = None
    message_id_incursions: int | None = None
    message_id_invasions: int | None = None
    message_id_earth_cycle: int | None = None
    message_id_open_world_cycles: int | None = None
    arbys_cache: CacheMeta = field(default_factory=CacheMeta)
    incursions_cache: CacheMeta = field(default_factory=CacheMeta)
    exports_cache: CacheMeta = field(default_factory=CacheMeta)
    dict_cache: CacheMeta = field(default_factory=CacheMeta)


class StateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> State:
        if not self.path.exists():
            return State()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return _state_from_dict(data)

    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _state_from_dict(data: dict[str, Any]) -> State:
    exports_cache = CacheMeta(**data.get("exports_cache", {}))
    dict_cache = CacheMeta(**data.get("dict_cache", {}))
    arbys_cache = CacheMeta(**data.get("arbys_cache", {}))
    incursions_cache = CacheMeta(**data.get("incursions_cache", {}))
    return State(
        last_hash_arbys=data.get("last_hash_arbys"),
        last_hash_incursions=data.get("last_hash_incursions"),
        last_hash_invasions=data.get("last_hash_invasions"),
        last_hash_earth_cycle=data.get("last_hash_earth_cycle"),
        last_hash_open_world_cycles=data.get("last_hash_open_world_cycles"),
        message_id_arbys=data.get("message_id_arbys"),
        message_id_incursions=data.get("message_id_incursions"),
        message_id_invasions=data.get("message_id_invasions"),
        message_id_earth_cycle=data.get("message_id_earth_cycle"),
        message_id_open_world_cycles=data.get("message_id_open_world_cycles"),
        arbys_cache=arbys_cache,
        incursions_cache=incursions_cache,
        exports_cache=exports_cache,
        dict_cache=dict_cache,
    )
