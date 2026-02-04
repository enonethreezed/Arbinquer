from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
import re
from email.utils import parsedate_to_datetime

import discord
import httpx
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from .diff import fingerprint
from .exports import build_node_map
from .parsers import parse_arbys, parse_incursions
from .sources import fetch_json_cached, fetch_text
from .storage import StateStore


@dataclass
class Config:
    discord_token: str
    channel_id: int
    lang: str
    tz_name: str
    poll_hour_minute: int
    poll_daily_time: time
    state_path: Path
    cache_dir: Path
    exports_url: str
    dict_url: str
    arbys_url: str
    incursions_url: str
    incursions_channel_id: int
    invasions_url: str
    invasions_channel_id: int
    earth_cycle_url: str
    cetus_cycle_url: str
    vallis_cycle_url: str
    cambion_cycle_url: str
    open_world_cycles_url: str
    earth_cycle_channel_id: int


def load_config() -> Config:
    load_dotenv(override=True)
    return Config(
        discord_token=_require("DISCORD_TOKEN"),
        channel_id=int(_require("CHANNEL_ID")),
        lang=os.getenv("LANG", "es"),
        tz_name=os.getenv("TZ", "Europe/Madrid"),
        poll_hour_minute=int(os.getenv("POLL_HOUR_MINUTE", "1")),
        poll_daily_time=_parse_time(os.getenv("POLL_DAILY_TIME", "00:01")),
        state_path=Path(os.getenv("STATE_PATH", "./state.json")),
        cache_dir=Path(os.getenv("CACHE_DIR", "./cache")),
        exports_url=os.getenv(
            "EXPORTS_URL",
            "https://browse.wf/warframe-public-export-plus/ExportRegions.json",
        ),
        dict_url=os.getenv(
            "DICT_URL",
            "https://browse.wf/warframe-public-export-plus/dict.es.json",
        ),
        arbys_url=os.getenv("ARBYS_URL", "https://browse.wf/arbys.txt"),
        incursions_url=os.getenv("INCURSIONS_URL", "https://browse.wf/sp-incursions.txt"),
        incursions_channel_id=int(os.getenv("INCURSIONS_CHANNEL_ID", "0")),
        invasions_url=os.getenv("INVASIONS_URL", "https://oracle.browse.wf/invasions"),
        invasions_channel_id=int(os.getenv("INVASIONS_CHANNEL_ID", "0")),
        earth_cycle_url=os.getenv("EARTH_CYCLE_URL", "https://api.warframestat.us/pc/earthCycle/"),
        cetus_cycle_url=os.getenv("CETUS_CYCLE_URL", "https://api.warframestat.us/pc/cetusCycle/"),
        vallis_cycle_url=os.getenv("VALLIS_CYCLE_URL", "https://api.warframestat.us/pc/vallisCycle/"),
        cambion_cycle_url=os.getenv("CAMBION_CYCLE_URL", "https://api.warframestat.us/pc/cambionCycle/"),
        open_world_cycles_url=os.getenv("OPEN_WORLD_CYCLES_URL", "https://api.warframestat.us/pc/"),
        earth_cycle_channel_id=int(os.getenv("EARTH_CYCLE_CHANNEL_ID", "0")),
    )


class ArbinquerBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.config = config
        self.store = StateStore(config.state_path)
        self.state = self.store.load()
        self.refresh_lock = asyncio.Lock()

    async def setup_hook(self) -> None:
        logging.info("setup_hook started")
        self.bg_tasks = [
            asyncio.create_task(self._initial_run()),
            asyncio.create_task(self._hourly_loop()),
            asyncio.create_task(self._invasions_loop()),
            asyncio.create_task(self._open_world_cycle_loop()),
        ]

    async def _initial_run(self) -> None:
        logging.info("initial run starting")
        await self.wait_until_ready()
        await self._refresh_all()
        await self._refresh_invasions(force_publish=True)
        await self._refresh_open_world_cycles(force_publish=True)
        logging.info("initial run complete")

    async def _cleanup_main_messages(self) -> None:
        cleaned = False
        if self.state.message_id_arbys:
            if await self._delete_message(self.state.message_id_arbys, self.config.channel_id):
                cleaned = True
        if self.state.message_id_incursions:
            if await self._delete_message(
                self.state.message_id_incursions,
                self.config.incursions_channel_id or self.config.channel_id,
            ):
                cleaned = True

        deleted_any = await self._delete_recent_bot_messages(self.config.channel_id, limit=200)
        if deleted_any:
            cleaned = True

        self.state.message_id_arbys = None
        self.state.last_hash_arbys = None
        self.state.message_id_incursions = None
        self.state.last_hash_incursions = None
        if cleaned:
            self.store.save(self.state)

    async def _cleanup_invasions_messages(self) -> None:
        cleaned = False
        if self.state.message_id_invasions:
            if await self._delete_message(
                self.state.message_id_invasions,
                self.config.invasions_channel_id,
            ):
                cleaned = True

        deleted_any = await self._delete_recent_bot_messages(
            self.config.invasions_channel_id,
            limit=200,
        )
        if deleted_any:
            cleaned = True

        self.state.message_id_invasions = None
        self.state.last_hash_invasions = None
        if cleaned:
            self.store.save(self.state)

    async def _cleanup_open_world_cycle_messages(self) -> None:
        cleaned = False
        if self.state.message_id_open_world_cycles:
            if await self._delete_message(
                self.state.message_id_open_world_cycles,
                self.config.earth_cycle_channel_id,
            ):
                cleaned = True

        deleted_any = await self._delete_recent_bot_messages(
            self.config.earth_cycle_channel_id,
            limit=200,
        )
        if deleted_any:
            cleaned = True

        self.state.message_id_open_world_cycles = None
        self.state.last_hash_open_world_cycles = None
        if cleaned:
            self.store.save(self.state)

    async def _hourly_loop(self) -> None:
        while True:
            await _sleep_until_next_hour_minute(self.config.poll_hour_minute)
            await self._refresh_all()

    async def _refresh_all(self) -> None:
        async with self.refresh_lock:
            await self._cleanup_main_messages()
            await self._run_arbitrations(force_publish=True)
            await self._run_incursions(force_publish=True)

    async def _invasions_loop(self) -> None:
        while True:
            await asyncio.sleep(300)
            await self._refresh_invasions(force_publish=False)

    async def _open_world_cycle_loop(self) -> None:
        while True:
            delay = await self._refresh_open_world_cycles(force_publish=False)
            await asyncio.sleep(delay)

    async def _refresh_invasions(self, force_publish: bool = False) -> None:
        if force_publish:
            await self._cleanup_invasions_messages()
        await self._run_invasions(force_publish=force_publish)

    async def _refresh_open_world_cycles(self, force_publish: bool = False) -> float:
        if force_publish:
            await self._cleanup_open_world_cycle_messages()
        return await self._run_open_world_cycles(force_publish=force_publish)

    async def _run_arbitrations(self, force_publish: bool = False) -> None:
        try:
            async with httpx.AsyncClient() as client:
                text, _, updated = await fetch_text(client, self.config.arbys_url, None)
                if not updated and not force_publish:
                    logging.info("arbys not modified")
                    return

                rows = parse_arbys(text)
                current = _select_current(rows, hours=1)
                if not current:
                    logging.warning("arbys no current row")
                    return

                node_map, _ = await self._load_node_map(client)
                payload = _format_arbitration(current, node_map, self.config.tz_name)
                new_hash = fingerprint(payload)
                if new_hash == self.state.last_hash_arbys and not force_publish:
                    logging.info("arbys unchanged")
                    return

                message_id = await self._post_or_edit(
                    payload,
                    self.state.message_id_arbys,
                    self.config.channel_id,
                )
                self.state.last_hash_arbys = new_hash
                self.state.message_id_arbys = message_id
                self.store.save(self.state)
                logging.info("arbys published (message %s)", message_id)
        except Exception:  # noqa: BLE001
            logging.exception("arbys update failed")

    async def _run_incursions(self, force_publish: bool = False) -> None:
        try:
            channel_id = self.config.incursions_channel_id or self.config.channel_id
            async with httpx.AsyncClient() as client:
                text, _, updated = await fetch_text(client, self.config.incursions_url, None)
                if not updated and not force_publish:
                    logging.info("incursions not modified")
                    return

                rows = parse_incursions(text)
                current = _select_current(rows, hours=24)
                if not current:
                    logging.warning("incursions no current row")
                    return

                node_map, _ = await self._load_node_map(client)
                payload = _format_incursions(current, node_map, self.config.tz_name)
                new_hash = fingerprint(payload)
                if new_hash == self.state.last_hash_incursions and not force_publish:
                    logging.info("incursions unchanged")
                    return

                message_id = await self._post_or_edit(
                    payload,
                    self.state.message_id_incursions,
                    channel_id,
                )
                self.state.last_hash_incursions = new_hash
                self.state.message_id_incursions = message_id
                self.store.save(self.state)
                logging.info("incursions published (message %s)", message_id)
        except Exception:  # noqa: BLE001
            logging.exception("incursions update failed")

    async def _run_invasions(self, force_publish: bool = False) -> None:
        try:
            if not self.config.invasions_channel_id:
                logging.warning("invasions channel not configured")
                return
            async with httpx.AsyncClient() as client:
                response = await client.get(self.config.invasions_url, timeout=20.0)
                response.raise_for_status()
                data = response.json()

                node_map, dictionary = await self._load_node_map(client)
                payload = _format_invasions(data, node_map, dictionary)
                new_hash = fingerprint(payload)
                if new_hash == self.state.last_hash_invasions and not force_publish:
                    logging.info("invasions unchanged")
                    return

                content = _format_invasions_message(payload)
                if new_hash != self.state.last_hash_invasions:
                    await self._delete_recent_bot_messages(self.config.invasions_channel_id, limit=200)
                message_id = await self._post_raw(
                    content,
                    self.state.message_id_invasions,
                    self.config.invasions_channel_id,
                )
                self.state.last_hash_invasions = new_hash
                self.state.message_id_invasions = message_id
                self.store.save(self.state)
                logging.info("invasions published (message %s)", message_id)
        except Exception:  # noqa: BLE001
            logging.exception("invasions update failed")

    async def _run_open_world_cycles(self, force_publish: bool = False) -> float:
        try:
            if not self.config.earth_cycle_channel_id:
                logging.warning("cycle channel not configured")
                return 300.0
            async with httpx.AsyncClient(follow_redirects=True) as client:
                cycles = await _fetch_open_world_cycles(client, self.config.open_world_cycles_url)
                earth = cycles.get("earthCycle", {})
                cetus = cycles.get("cetusCycle", {})
                vallis = cycles.get("vallisCycle", {})
                cambion = cycles.get("cambionCycle", {})

                payload = _format_open_world_cycles(earth, cetus, vallis, cambion)
                new_hash = fingerprint(payload)
                if new_hash == self.state.last_hash_open_world_cycles and not force_publish:
                    logging.info("open world cycles unchanged")
                    return _next_cycle_delay(payload)

                content = _format_open_world_cycles_message(payload)
                if new_hash != self.state.last_hash_open_world_cycles:
                    await self._delete_recent_bot_messages(self.config.earth_cycle_channel_id, limit=200)
                message_id = await self._post_raw(
                    content,
                    self.state.message_id_open_world_cycles,
                    self.config.earth_cycle_channel_id,
                )
                self.state.last_hash_open_world_cycles = new_hash
                self.state.message_id_open_world_cycles = message_id
                self.store.save(self.state)
                logging.info("open world cycles published (message %s)", message_id)
                return _next_cycle_delay(payload)
        except Exception:  # noqa: BLE001
            logging.exception("open world cycles update failed")
            return 300.0

    async def _load_node_map(self, client: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, str] | None]:
        exports_path = self.config.cache_dir / "ExportRegions.json"
        dict_path = self.config.cache_dir / f"dict.{self.config.lang}.json"

        exports, exports_meta = await fetch_json_cached(
            client,
            self.config.exports_url,
            exports_path,
            self.state.exports_cache,
        )
        self.state.exports_cache = exports_meta

        dictionary = None
        if self.config.dict_url:
            dictionary, dict_meta = await fetch_json_cached(
                client,
                self.config.dict_url,
                dict_path,
                self.state.dict_cache,
            )
            self.state.dict_cache = dict_meta

        self.store.save(self.state)
        return build_node_map(exports, dictionary), dictionary

    async def _post_or_edit(
        self,
        payload: dict[str, Any],
        message_id: int | None,
        channel_id: int,
    ) -> int:
        channel = await self._get_channel(channel_id)
        content = _format_message(payload)

        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(content=content)
                return message.id
            except discord.NotFound:
                pass

        message = await channel.send(content=content)
        return message.id

    async def _post_raw(
        self,
        content: str,
        message_id: int | None,
        channel_id: int,
    ) -> int:
        channel = await self._get_channel(channel_id)
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(content=content)
                return message.id
            except discord.NotFound:
                pass

        message = await channel.send(content=content)
        return message.id

    async def _delete_message(self, message_id: int, channel_id: int) -> bool:
        try:
            channel = await self._get_channel(channel_id)
            message = await channel.fetch_message(message_id)
            await message.delete()
            logging.info("deleted previous message %s", message_id)
            return True
        except discord.NotFound:
            logging.info("previous message %s not found", message_id)
            return False
        except discord.Forbidden:
            logging.warning("missing permission to delete message %s", message_id)
            return False
        except Exception:  # noqa: BLE001
            logging.exception("failed to delete message %s", message_id)
            return False

    async def _delete_recent_bot_messages(self, channel_id: int, limit: int = 50) -> bool:
        try:
            channel = await self._get_channel(channel_id)
            deleted = False
            async for message in channel.history(limit=limit):
                if message.author and self.user and message.author.id == self.user.id:
                    try:
                        await message.delete()
                        deleted = True
                        await asyncio.sleep(0.6)
                    except discord.Forbidden:
                        logging.warning("missing permission to delete message %s", message.id)
                        return deleted
            if deleted:
                logging.info("deleted recent bot messages")
            return deleted
        except discord.Forbidden:
            logging.warning("missing permission to read message history")
            return False
        except Exception:  # noqa: BLE001
            logging.exception("failed to delete recent bot messages")
            return False

    async def _get_channel(self, channel_id: int) -> discord.TextChannel:
        channel = self.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            channel = await self.fetch_channel(channel_id)
        return channel


def _format_message(payload: dict[str, Any]) -> str:
    lines = [f"# {payload['emoji']} {payload['title']}", "------------------------------"]
    lines.append(f"- 📍 Location: {payload['location']}")
    if payload.get("mission"):
        lines.append(f"- 🧭 Mission: {payload['mission']}")
    lines.append(f"- ⏱ Start: {payload['start']}")
    if payload.get("next_change"):
        lines.append(f"- 🔄 Next change: {payload['next_change']}")
    if payload.get("extra"):
        extra = payload["extra"]
        if isinstance(extra, list):
            lines.append("- 🧭 Incursions:")
            for item in extra:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- 🧭 {extra}")
    lines.append("------------------------------")
    lines.append("Thanks to https://browse.wf/about for their great work.")
    lines.append("")
    return "\n".join(lines)


def _format_arbitration(entry: Any, node_map: dict[str, Any], tz_name: str) -> dict[str, Any]:
    node = node_map.get(entry.node_id)
    location = _format_node(node, entry.node_id)
    start = _format_time(entry.start_ts, tz_name)
    mission = _mission_name(node)
    if mission:
        mission = _title_case(mission)
    next_change = _relative_time(entry.start_ts + 3600)
    return {
        "title": "Arbitration",
        "emoji": "⚔️",
        "location": location,
        "mission": mission,
        "start": start,
        "next_change": next_change,
    }


def _format_incursions(entry: Any, node_map: dict[str, Any], tz_name: str) -> dict[str, Any]:
    nodes = [
        _format_node_with_mission(node_map.get(node_id), node_id)
        for node_id in entry.node_ids
    ]
    start = _format_time(entry.start_ts, tz_name)
    next_change = _relative_time(entry.start_ts + 86400)
    return {
        "title": "Steel Path Incursions",
        "emoji": "🛡️",
        "location": "Multiple nodes",
        "start": start,
        "extra": nodes,
        "next_change": next_change,
    }


def _format_node(node: Any, node_id: str) -> str:
    if node is None:
        return node_id
    if node.planet:
        return f"{node.name} ({node.planet})"
    return node.name


def _mission_name(node: Any) -> str | None:
    if node is None:
        return None
    return node.mission


def _format_node_with_mission(node: Any, node_id: str) -> str:
    base = _format_node(node, node_id)
    if node is None or not node.mission:
        return base
    return f"{base} — {_title_case(node.mission)}"


def _format_invasions(data: dict[str, Any], node_map: dict[str, Any], dictionary: dict[str, str] | None) -> dict[str, Any]:
    invasions = data.get("invasions", [])
    grouped = {}
    for item in invasions:
        invasion_id = item.get("id")
        if not invasion_id:
            continue
        grouped.setdefault(invasion_id, []).append(item)

    rows: list[tuple[str, str, str]] = []
    for _, sides in grouped.items():
        if not sides:
            continue
        node_id = sides[0].get("node")
        node = node_map.get(node_id)
        location = _format_node(node, node_id or "Unknown")

        sorted_sides = sorted(sides, key=lambda s: _faction_name(s.get("ally")))
        side_texts = [_format_invasion_side(side, dictionary) for side in sorted_sides]
        side_a = side_texts[0] if len(side_texts) > 0 else ""
        side_b = side_texts[1] if len(side_texts) > 1 else ""
        rows.append((location, side_a, side_b))

    return {"rows": rows}


def _format_invasions_message(payload: dict[str, Any]) -> str:
    lines = ["# ⚠️ Invasions", "------------------------------"]
    for node, side_a, side_b in payload.get("rows", []):
        parts = []
        if side_a:
            parts.append(side_a)
        if side_b:
            parts.append(side_b)
        joined = " | ".join(parts)
        lines.append(f"**🛰️ {node}** — {joined}")
    lines.append("------------------------------")
    lines.append("- 🔄 Next check: 5m")
    lines.append("Thanks to https://browse.wf/about for their great work.")
    lines.append("")
    return "\n".join(lines)


def _format_invasion_side(side: dict[str, Any], dictionary: dict[str, str] | None) -> str:
    ally = _faction_name(side.get("ally"))
    ally = f"***{ally}***"
    missions = side.get("missions", [])
    mission_text = " / ".join(_title_case(_friendly_mission(m)) for m in missions)
    rewards = _format_rewards(side.get("allyPay", []), dictionary)
    if rewards:
        return f"{ally}: {mission_text} — {rewards}"
    return f"{ally}: {mission_text}"


def _format_rewards(items: list[dict[str, Any]], dictionary: dict[str, str] | None) -> str:
    rewards: list[str] = []
    for item in items:
        item_type = item.get("ItemType")
        count = item.get("ItemCount")
        name = _item_name(item_type, dictionary)
        if not name:
            continue
        if count and isinstance(count, int) and count > 1:
            rewards.append(f"{name} x{count}")
        else:
            rewards.append(name)
    return ", ".join(rewards)


def _item_name(item_type: str | None, dictionary: dict[str, str] | None) -> str | None:
    if not item_type:
        return None
    if dictionary and item_type in dictionary:
        return dictionary[item_type]
    name = item_type.rsplit("/", 1)[-1]
    return _title_case(_split_camel(name))


def _split_camel(text: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", text)


def _friendly_mission(text: str) -> str:
    return _split_camel(text)


def _faction_name(code: str | None) -> str:
    mapping = {
        "FC_CORPUS": "Corpus",
        "FC_GRINEER": "Grineer",
        "FC_INFESTATION": "Infestation",
        "FC_OROKIN": "Orokin",
        "FC_MITW": "MurMur",
        "FC_SENTIENT": "Sentient",
    }
    if not code:
        return "Unknown"
    return mapping.get(code, code)


def _format_earth_cycle(data: dict[str, Any]) -> dict[str, Any]:
    state = data.get("state") or ("day" if data.get("isDay") else "night")
    time_left = data.get("timeLeft") or "unknown"
    expiry = data.get("expiry")
    activation = data.get("activation")
    return {
        "state": str(state),
        "timeLeft": str(time_left),
        "expiry": expiry,
        "activation": activation,
    }


def _format_earth_cycle_message(payload: dict[str, Any]) -> str:
    state = payload.get("state", "unknown").title()
    time_left = payload.get("timeLeft", "unknown")
    lines = ["# 🌍 Earth Cycle", "------------------------------"]
    lines.append(f"- 🌓 State: {state}")
    lines.append(f"- ⏳ Time left: {time_left}")
    lines.append("------------------------------")
    lines.append("Thanks to https://browse.wf/about for their great work.")
    lines.append("")
    return "\n".join(lines)


async def _fetch_open_world_cycles(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url, timeout=20.0)
    response.raise_for_status()
    data = response.json()
    server_now = _parse_http_date(response.headers.get("Date"))
    if server_now:
        for key in ("earthCycle", "cetusCycle", "vallisCycle", "cambionCycle"):
            if key in data and isinstance(data[key], dict):
                data[key]["_server_now"] = server_now
    return data


def _format_open_world_cycles(
    earth: dict[str, Any],
    cetus: dict[str, Any],
    vallis: dict[str, Any],
    cambion: dict[str, Any],
) -> dict[str, Any]:
    return {
        "earth": _format_cycle_entry("Earth", earth),
        "cetus": _format_cycle_entry("Cetus", cetus),
        "vallis": _format_cycle_entry("Orb Vallis", vallis),
        "cambion": _format_cycle_entry("Cambion", cambion),
    }


def _format_cycle_entry(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if name == "Orb Vallis":
        return {
            "name": name,
            "state": "Fixing",
            "timeLeft": "",
            "expiry": None,
        }
    state = data.get("state") or ("day" if data.get("isDay") else "night")
    expiry = _parse_expiry(data.get("expiry"))
    activation = _parse_expiry(data.get("activation"))
    server_now = data.get("_server_now")
    now = server_now if isinstance(server_now, (int, float)) else datetime.now(timezone.utc).timestamp()
    time_left = data.get("timeLeft")
    if not time_left and expiry and expiry >= now:
        time_left = _format_seconds(max(0.0, expiry - now))
    if not time_left:
        time_left = "unknown"
    return {
        "name": name,
        "state": str(state).title(),
        "timeLeft": str(time_left),
        "expiry": expiry,
    }


def _format_open_world_cycles_message(payload: dict[str, Any]) -> str:
    lines = ["# 🌍 Open World Cycles", "------------------------------"]
    for key in ("earth", "cetus", "vallis", "cambion"):
        entry = payload.get(key, {})
        name = entry.get("name", key.title())
        state = entry.get("state", "Unknown")
        time_left = entry.get("timeLeft", "unknown")
        if time_left:
            lines.append(f"- **{name}**: {state} ({time_left})")
        else:
            lines.append(f"- **{name}**: {state}")
    next_change = _next_cycle_delay(payload)
    lines.append(f"- 🔄 Next change: {_format_seconds(next_change)}")
    lines.append("------------------------------")
    lines.append("Thanks to https://browse.wf/about for their great work.")
    lines.append("")
    return "\n".join(lines)


def _next_cycle_delay(payload: dict[str, Any]) -> float:
    now = datetime.now(timezone.utc).timestamp()
    expiries = []
    for key in ("earth", "cetus", "vallis", "cambion"):
        expiry = payload.get(key, {}).get("expiry")
        if isinstance(expiry, (int, float)):
            if expiry >= now:
                expiries.append(expiry)
    if not expiries:
        return 300.0
    next_expiry = min(expiries)
    delay = max(30.0, next_expiry - now + 5.0)
    return delay


def _parse_expiry(value: Any) -> float | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _parse_http_date(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None


def _format_seconds(seconds: float) -> str:
    total = int(max(seconds, 0))
    if total == 0:
        return "0m"

    minutes_total = (total + 59) // 60
    hours = minutes_total // 60
    days = hours // 24
    if days > 0:
        return f"{days}d {hours % 24}h"
    if hours > 0:
        return f"{hours}h {minutes_total % 60}m"
    return f"{minutes_total}m"


def _title_case(text: str) -> str:
    return " ".join(word.capitalize() for word in text.split())


def _format_time(ts: int, tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
    return f"{dt.strftime('%Y-%m-%d %H:%M %Z')} ({_relative_time(ts)})"


def _relative_time(ts: int) -> str:
    now = datetime.now(timezone.utc).timestamp()
    delta = int(ts - now)
    if delta == 0:
        return "now"

    suffix = "in" if delta > 0 else "ago"
    seconds = abs(delta)
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{suffix} {days}d {hours % 24}h"
    if hours > 0:
        return f"{suffix} {hours}h {minutes % 60}m"
    return f"{suffix} {minutes}m"


def _select_current(rows: list[Any], hours: int) -> Any | None:
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r.start_ts)
    now = datetime.now(timezone.utc).timestamp()
    window = hours * 3600
    for row in reversed(rows):
        if row.start_ts <= now < row.start_ts + window:
            return row
    for row in rows:
        if row.start_ts > now:
            return row
    return rows[-1]


async def _sleep_until_next_hour_minute(minute: int) -> None:
    now = datetime.now(timezone.utc)
    target = now.replace(minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(hours=1)
    await asyncio.sleep((target - now).total_seconds())


async def _sleep_until_next_daily_time(target_time: time) -> None:
    now = datetime.now(timezone.utc)
    target = datetime.combine(now.date(), target_time, tzinfo=timezone.utc)
    if target <= now:
        target = target + timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute), tzinfo=timezone.utc)


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"missing env var {key}")
    return value


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    )
    config = load_config()
    bot = ArbinquerBot(config)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
