# Arbinquer

Discord bot that posts Warframe Arbitrations, Steel Path Incursions, Invasions,
and open-world cycles. Data comes from browse.wf and WarframeStat.

## Data Sources

- Arbitrations: `https://browse.wf/arbys.txt`
- Steel Path Incursions: `https://browse.wf/sp-incursions.txt`
- Invasions: `https://oracle.browse.wf/invasions`
- Open-world cycles (Earth/Cetus/Orb Vallis/Cambion): `https://api.warframestat.us/pc/`
- Node names: `https://browse.wf/warframe-public-export-plus/ExportRegions.json`
- Localization: `https://browse.wf/warframe-public-export-plus/dict.en.json`

## Requirements

- Python 3.12 (see `.python-version`)
- `pip` for dependency install

## Setup

1. Install dependencies:
   - `python -m pip install -r requirements.txt`

2. Configure environment:
   - Copy `.env.example` to `.env` and fill values.
   - Put the bot token in `.discord.token` (format: `Token=...`).
   - Use `.discord.token.sample` as reference.

3. Ensure the bot has permissions in the target channels:
   - View Channel
   - Send Messages
   - Read Message History (for edits/deletes)
   - Manage Messages (for cleanup)

## Run

Use `botctl.sh` to run the bot in background and keep a log in the repo root:

- Start: `./botctl.sh start`
- Stop: `./botctl.sh stop`
- Restart: `./botctl.sh restart`
- Status: `./botctl.sh status`

Artifacts:
- Log file: `arbinquer.log`
- PID file: `arbinquer.pid`

## Refresh Cadence

- Arbitrations: hourly at `HH:01` UTC
- Incursions: hourly at `HH:01` UTC (separate channel)
- Invasions: every 5 minutes (only posts on change)
- Open-world cycles: rescheduled to the nearest upcoming cycle change

## Channels

Configured via `.env`:

- `CHANNEL_ID`: Arbitrations channel
- `INCURSIONS_CHANNEL_ID`: Incursions channel
- `INVASIONS_CHANNEL_ID`: Invasions channel
- `EARTH_CYCLE_CHANNEL_ID`: Open-world cycles channel

## Troubleshooting

- If messages do not appear, check `arbinquer.log`.
- If you see rate limits, reduce cleanup scope or frequency.
- If the bot cannot post or delete, fix channel permissions.

## Message Examples

Arbitration:

```
# ⚔️ Arbitration
------------------------------
- 📍 Location: Munio (Deimos)
- 🧭 Mission: Mirror Defense
- ⏱ Start: 2026-02-03 20:00 CET (ago 27m)
- 🔄 Next change: in 33m
------------------------------
Thanks to https://browse.wf/about for their great work.
```

Steel Path Incursions:

```
# 🛡️ Steel Path Incursions
------------------------------
- 📍 Location: Multiple nodes
- ⏱ Start: 2026-02-03 01:00 CET (ago 19h 27m)
- 🔄 Next change: in 4h 33m
- 🧭 Incursions:
  - Pacific (Earth) — Rescue
  - Sharpless (Phobos) — Mobile Defense
  - Baal (Europa) — Exterminate
------------------------------
Thanks to https://browse.wf/about for their great work.
```

Invasions:

```
# ⚠️ Invasions
------------------------------
**🛰️ Bode (Ceres)** — ***Corpus***: Exterminate / Territory — Snipetron Vandal Blueprint | ***Grineer***: Defense / Exterminate — Grineer Combat Knife Hilt
**🛰️ Carpo (Jupiter)** — ***Grineer***: Territory / Territory — Chem Component x3 | ***Corpus***: Mobile Defense / Mobile Defense — Energy Component x3
------------------------------
- 🔄 Next check: 5m
Thanks to https://browse.wf/about for their great work.
```

Open World Cycles:

```
# 🌍 Open World Cycles
------------------------------
- **Earth**: Day (2h 3m 35s)
- **Cetus**: Day (1h 12m 35s)
- **Orb Vallis**: Fixing
- **Cambion**: Fass (1h 12m 35s)
- 🔄 Next change: 11m
------------------------------
Thanks to https://browse.wf/about for their great work.
```

## Acknowledgments

Thanks to https://browse.wf/about for their great work.

## Orb Vallis Note

Orb Vallis timing can be inconsistent across public sources. While the bot uses
WarframeStat (`/pc`) for cycles, the reported state/time can differ from other
apps or in-game displays. For now, Orb Vallis is marked as "Fixing" until a
stable, matching source is confirmed.
