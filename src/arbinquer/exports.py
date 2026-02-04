from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NodeInfo:
    node_id: str
    name: str
    planet: str | None = None
    mission: str | None = None


def build_node_map(exports: dict[str, Any], dictionary: dict[str, str] | None = None) -> dict[str, NodeInfo]:
    if _looks_like_node_map(exports):
        return _build_from_node_map(exports, dictionary)

    nodes = _find_nodes_list(exports)
    result: dict[str, NodeInfo] = {}
    for item in nodes:
        node_id = _first_key(item, ["Node", "node", "nodeId", "node_id", "NodeId"])
        if not node_id:
            continue
        raw_name = _first_key(item, ["Name", "name", "nodeName", "NodeName", "nameKey"])
        name = _resolve_name(raw_name, dictionary)
        if not name:
            name = node_id
        raw_planet = _first_key(item, ["systemName", "SystemName", "Planet", "planet", "Region", "region", "system"])
        planet = _resolve_name(raw_planet, dictionary)
        raw_mission = _first_key(item, ["missionName", "MissionName", "mission", "Mission"])
        mission = _resolve_name(raw_mission, dictionary)
        result[node_id] = NodeInfo(node_id=node_id, name=name, planet=planet, mission=mission)
    return result


def _resolve_name(name: str | None, dictionary: dict[str, str] | None) -> str | None:
    if not name:
        return None
    if dictionary and name in dictionary:
        return dictionary[name]
    if name.startswith("/Lotus/Language/"):
        return name.rsplit("/", 1)[-1]
    return name


def _looks_like_node_map(data: dict[str, Any]) -> bool:
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if "name" in value or "systemName" in value:
            return True
    return False


def _build_from_node_map(data: dict[str, Any], dictionary: dict[str, str] | None) -> dict[str, NodeInfo]:
    result: dict[str, NodeInfo] = {}
    for node_id, item in data.items():
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name") or item.get("Name")
        name = _resolve_name(raw_name, dictionary) or node_id
        raw_planet = item.get("systemName") or item.get("SystemName")
        planet = _resolve_name(raw_planet, dictionary)
        raw_mission = item.get("missionName") or item.get("MissionName")
        mission = _resolve_name(raw_mission, dictionary)
        result[node_id] = NodeInfo(node_id=node_id, name=name, planet=planet, mission=mission)
    return result


def _first_key(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        if key in item and isinstance(item[key], str):
            return item[key]
    return None


def _find_nodes_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "Nodes" in data and isinstance(data["Nodes"], list):
        return [n for n in data["Nodes"] if isinstance(n, dict)]

    found: list[dict[str, Any]] = []
    _walk(data, found)
    return found


def _walk(value: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if "Nodes" in value and isinstance(value["Nodes"], list):
            found.extend([n for n in value["Nodes"] if isinstance(n, dict)])
        for child in value.values():
            _walk(child, found)
    elif isinstance(value, list):
        for child in value:
            _walk(child, found)
