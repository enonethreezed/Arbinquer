from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArbitrationHour:
    start_ts: int
    node_id: str


@dataclass
class IncursionDay:
    start_ts: int
    node_ids: list[str]


def parse_arbys(text: str) -> list[ArbitrationHour]:
    rows: list[ArbitrationHour] = []
    for line in _lines(text):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            continue
        ts = _to_int(parts[0])
        node_id = parts[1]
        if ts is None or not node_id:
            continue
        rows.append(ArbitrationHour(start_ts=ts, node_id=node_id))
    return rows


def parse_incursions(text: str) -> list[IncursionDay]:
    rows: list[IncursionDay] = []
    for line in _lines(text):
        parts = [p.strip() for p in line.split(";")]
        if len(parts) != 2:
            continue
        ts = _to_int(parts[0])
        nodes = [n.strip() for n in parts[1].split(",") if n.strip()]
        if ts is None or not nodes:
            continue
        rows.append(IncursionDay(start_ts=ts, node_ids=nodes))
    return rows


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
