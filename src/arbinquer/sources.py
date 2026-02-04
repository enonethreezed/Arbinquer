from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import httpx

from .storage import CacheMeta


class FetchError(RuntimeError):
    pass


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    cache_meta: CacheMeta | None = None,
    timeout: float = 20.0,
) -> tuple[str, CacheMeta, bool]:
    headers = {}
    if cache_meta and cache_meta.etag:
        headers["If-None-Match"] = cache_meta.etag
    if cache_meta and cache_meta.last_modified:
        headers["If-Modified-Since"] = cache_meta.last_modified

    response = await client.get(url, headers=headers, timeout=timeout)
    if response.status_code == 304 and cache_meta is not None:
        return "", cache_meta, False
    response.raise_for_status()

    new_meta = CacheMeta(
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )
    return response.text, new_meta, True


async def fetch_json_cached(
    client: httpx.AsyncClient,
    url: str,
    cache_path: Path,
    cache_meta: CacheMeta | None = None,
    timeout: float = 20.0,
) -> tuple[dict[str, Any], CacheMeta]:
    text, new_meta, updated = await fetch_text(client, url, cache_meta, timeout=timeout)
    if updated:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
        return json.loads(text), new_meta

    if not cache_path.exists():
        text, new_meta, _ = await fetch_text(client, url, None, timeout=timeout)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
        return json.loads(text), new_meta

    return json.loads(cache_path.read_text(encoding="utf-8")), new_meta


async def fetch_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    retries: int = 3,
    base_delay: float = 2.0,
) -> str:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(url, timeout=20.0)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries:
                break
            delay = base_delay * (2**attempt)
            jitter = random.uniform(0.0, 0.5 * base_delay)
            await httpx.AsyncClient().aclose()
            await _sleep(delay + jitter)
    raise FetchError(str(last_exc))


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
