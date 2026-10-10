"""Rule settings from the console: switch plugin rules on and off (e.g. a site that doesn't care about
smoking) and change how they fire (duration, severity, cooldown, capacity, working hours).

The settings are stored in Postgres and mirrored to Redis, where the event engine reads them:
  rules:settings:<plugin_id>   hash rule_id -> {"enabled": bool, <changed fields>} as JSON
                               (event_engine/main.py re-reads it every 2 s)
Redis isn't persistent, so the backend rewrites the hash at startup and every RESYNC_S seconds.
A rule with "enabled": false or "planned": true in the plugin isn't usable yet and can't be changed here.
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

import auth
from models import RuleSetting, SessionLocal, User, iso

PLUGINS_DIR = os.getenv("PLUGINS_DIR", "/app/plugins")
PLUGIN_ID = os.getenv("PLUGIN_ID", "construction_safety")
SITE_TIMEZONE = os.getenv("SITE_TIMEZONE", "Africa/Cairo")
SETTINGS_KEY = "rules:settings:{plugin_id}"
RESYNC_S = 30
# fields the console may change; keep in sync with event_engine/rules.py:RULE_SETTINGS
RULE_SETTINGS = ("min_duration_s", "severity", "cooldown_s", "max_count", "active_hours")
DEFAULT_COOLDOWN_S = 10.0   # event_engine RULE_COOLDOWN_SECONDS

router = APIRouter(prefix="/rules", tags=["rules"])
_redis: aioredis.Redis | None = None


class ActiveHours(BaseModel):
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: list[int] = Field(min_length=1, max_length=7)   # Monday = 0

    @field_validator("days")
    @classmethod
    def valid_days(cls, days):
        if any(d < 0 or d > 6 for d in days):
            raise ValueError("days are 0 (Monday) to 6 (Sunday)")
        return sorted(set(days))


class RuleChange(BaseModel):
    """Only the fields sent are changed. null resets a field to the plugin's default."""
    enabled: bool | None = None
    min_duration_s: float | None = Field(None, ge=0, le=3600)
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] | None = None
    cooldown_s: float | None = Field(None, ge=0, le=3600)
    max_count: int | None = Field(None, ge=0, le=100)
    active_hours: ActiveHours | None = None


def load_plugin() -> dict | None:
    for path in Path(PLUGINS_DIR).glob("*.json"):
        plugin = json.loads(path.read_text())
        if plugin.get("plugin_id") == PLUGIN_ID:
            return plugin
    return None


def usable(rule: dict) -> bool:
    return rule.get("enabled", True) and not rule.get("planned", False)


def defaults(rule: dict) -> dict:
    return {"min_duration_s": rule.get("min_duration_s", 0), "severity": rule["severity"],
            "cooldown_s": rule.get("cooldown_s", DEFAULT_COOLDOWN_S), "max_count": rule.get("max_count"),
            "active_hours": rule.get("active_hours")}


def _engine_value(row: RuleSetting) -> str:
    return json.dumps({"enabled": row.enabled, **(row.overrides or {})})


async def _rows(session) -> dict[str, RuleSetting]:
    rows = (await session.scalars(select(RuleSetting).where(RuleSetting.plugin_id == PLUGIN_ID))).all()
    return {row.rule_id: row for row in rows}


async def sync_redis():
    """Copy the settings from Postgres to Redis."""
    async with SessionLocal() as session:
        rows = await _rows(session)
    key = SETTINGS_KEY.format(plugin_id=PLUGIN_ID)
    async with _redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if rows:
            pipe.hset(key, mapping={rule_id: _engine_value(row) for rule_id, row in rows.items()})
        await pipe.execute()


async def keep_synced(redis_url: str):
    """Runs for the backend's lifetime, so a Redis restart doesn't quietly undo the settings."""
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            await sync_redis()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Backend] Couldn't sync rule settings to Redis: {e}", flush=True)
        await asyncio.sleep(RESYNC_S)


async def close():
    if _redis:
        await _redis.aclose()


def _rule_dict(plugin: dict, rule: dict, row: RuleSetting | None) -> dict:
    available = usable(rule)
    zone = plugin.get("zones", {}).get(rule.get("zone")) if rule.get("zone") else None
    base = defaults(rule)
    overrides = (row.overrides or {}) if row else {}
    return {
        "rule_id": rule["rule_id"],
        "name": rule.get("name") or rule["event_type"].replace("_", " ").capitalize(),
        "type": rule.get("type"),
        "description": rule.get("description", ""),
        "event_type": rule["event_type"],
        "zone_id": rule.get("zone") if zone else None,
        "zone_name": zone["name"] if zone else None,
        "available": available,
        "planned": bool(rule.get("planned")),
        "requires": rule.get("requires"),
        "enabled": available and (row.enabled if row else True),
        **{k: overrides.get(k, base[k]) for k in RULE_SETTINGS},
        "defaults": base,
        "changed": sorted(overrides),
        "changed_by": row.changed_by if row else None,
        "changed_at": iso(row.changed_at) if row else None,
    }


@router.get("")
async def list_rules():
    plugin = load_plugin()
    if not plugin:
        raise HTTPException(status_code=503, detail=f"Plugin '{PLUGIN_ID}' not found")
    async with SessionLocal() as session:
        rows = await _rows(session)
    return {"plugin_id": PLUGIN_ID, "plugin_name": plugin.get("name", PLUGIN_ID), "timezone": SITE_TIMEZONE,
            "rules": [_rule_dict(plugin, r, rows.get(r["rule_id"])) for r in plugin.get("rules", [])],
            # for the console's other languages: zone ids (incidents carry the English zone name) and the
            # plugin's own translations of rule and zone names (docs/plugins.md)
            "zones": {zid: z.get("name", zid) for zid, z in plugin.get("zones", {}).items()},
            "translations": plugin.get("translations", {})}


@router.patch("/{rule_id}")
async def change_rule(rule_id: str, body: RuleChange, me: User = Depends(auth.can_handle_incidents)):
    plugin = load_plugin()
    rule = next((r for r in (plugin or {}).get("rules", []) if r["rule_id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if not usable(rule):
        raise HTTPException(status_code=409, detail="This rule isn't available yet, so it can't be changed")
    sent = body.model_fields_set
    if "max_count" in sent and rule.get("max_count") is None:
        raise HTTPException(status_code=422, detail="This rule has no maximum count")
    if body.active_hours and body.active_hours.start == body.active_hours.end:
        raise HTTPException(status_code=422, detail="Working hours must start and end at different times")

    async with SessionLocal() as session:
        row = await session.get(RuleSetting, (PLUGIN_ID, rule_id))
        if not row:
            row = RuleSetting(plugin_id=PLUGIN_ID, rule_id=rule_id, enabled=True, overrides={})
            session.add(row)
        if "enabled" in sent and body.enabled is not None:
            row.enabled = body.enabled
        overrides = dict(row.overrides or {})
        base = defaults(rule)
        for field in sent & set(RULE_SETTINGS):
            value = getattr(body, field)
            value = value.model_dump() if isinstance(value, BaseModel) else value
            if value is None or value == base[field]:
                overrides.pop(field, None)    # back to the plugin's default
            else:
                overrides[field] = value
        row.overrides = overrides
        row.changed_by = me.name
        row.changed_at = datetime.utcnow()
        await session.commit()

    try:
        await _redis.hset(SETTINGS_KEY.format(plugin_id=PLUGIN_ID), rule_id, _engine_value(row))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} changed {rule_id}: enabled={row.enabled} {overrides}", flush=True)
    return _rule_dict(plugin, rule, row)
