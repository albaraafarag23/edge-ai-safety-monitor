"""Switching plugin rules on and off from the console (e.g. a site that doesn't care about smoking).

The switches are stored in Postgres and mirrored to Redis, where the event engine reads them:
  rules:off:<plugin_id>      set of rule ids switched off (event_engine/main.py refreshes it every 2 s)
Redis isn't persistent, so the backend copies the switches to it at startup and every RESYNC_S seconds.
A rule with "enabled": false in the plugin JSON isn't usable yet (e.g. the model lacks its classes)
and can't be switched on here.
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import auth
from models import RuleSwitch, SessionLocal, User, iso

PLUGINS_DIR = os.getenv("PLUGINS_DIR", "/app/plugins")
PLUGIN_ID = os.getenv("PLUGIN_ID", "construction_safety")
SWITCHED_OFF_KEY = "rules:off:{plugin_id}"
RESYNC_S = 30

router = APIRouter(prefix="/rules", tags=["rules"])
_redis: aioredis.Redis | None = None


class SwitchIn(BaseModel):
    enabled: bool


def load_plugin() -> dict | None:
    for path in Path(PLUGINS_DIR).glob("*.json"):
        plugin = json.loads(path.read_text())
        if plugin.get("plugin_id") == PLUGIN_ID:
            return plugin
    return None


async def _switches(session) -> dict[str, RuleSwitch]:
    rows = (await session.scalars(select(RuleSwitch).where(RuleSwitch.plugin_id == PLUGIN_ID))).all()
    return {row.rule_id: row for row in rows}


async def sync_redis():
    """Copy the switches from Postgres to Redis."""
    async with SessionLocal() as session:
        off = [rule_id for rule_id, row in (await _switches(session)).items() if not row.enabled]
    key = SWITCHED_OFF_KEY.format(plugin_id=PLUGIN_ID)
    async with _redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if off:
            pipe.sadd(key, *off)
        await pipe.execute()


async def keep_synced(redis_url: str):
    """Runs for the backend's lifetime, so a Redis restart doesn't quietly switch rules back on."""
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            await sync_redis()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Backend] Couldn't sync rule switches to Redis: {e}", flush=True)
        await asyncio.sleep(RESYNC_S)


async def close():
    if _redis:
        await _redis.aclose()


def _rule_dict(plugin: dict, rule: dict, switch: RuleSwitch | None) -> dict:
    available = rule.get("enabled", True)
    zone = plugin.get("zones", {}).get(rule.get("zone")) if rule.get("zone") else None
    return {
        "rule_id": rule["rule_id"],
        "type": rule.get("type"),
        "description": rule.get("description", ""),
        "event_type": rule.get("event_type"),
        "severity": rule.get("severity"),
        "zone_name": zone["name"] if zone else None,
        "min_duration_s": rule.get("min_duration_s", 0),
        "available": available,
        "enabled": available and (switch.enabled if switch else True),
        "changed_by": switch.changed_by if switch else None,
        "changed_at": iso(switch.changed_at) if switch else None,
    }


@router.get("")
async def list_rules():
    plugin = load_plugin()
    if not plugin:
        raise HTTPException(status_code=503, detail=f"Plugin '{PLUGIN_ID}' not found")
    async with SessionLocal() as session:
        switches = await _switches(session)
    return {"plugin_id": PLUGIN_ID, "plugin_name": plugin.get("name", PLUGIN_ID),
            "rules": [_rule_dict(plugin, r, switches.get(r["rule_id"])) for r in plugin.get("rules", [])]}


@router.put("/{rule_id}")
async def switch_rule(rule_id: str, body: SwitchIn, me: User = Depends(auth.can_handle_incidents)):
    plugin = load_plugin()
    rule = next((r for r in (plugin or {}).get("rules", []) if r["rule_id"] == rule_id), None)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if body.enabled and not rule.get("enabled", True):
        raise HTTPException(status_code=409, detail="This rule isn't available yet, so it can't be switched on")

    async with SessionLocal() as session:
        switch = await session.get(RuleSwitch, (PLUGIN_ID, rule_id))
        if not switch:
            switch = RuleSwitch(plugin_id=PLUGIN_ID, rule_id=rule_id)
            session.add(switch)
        switch.enabled = body.enabled
        switch.changed_by = me.name
        switch.changed_at = datetime.utcnow()
        await session.commit()

    key = SWITCHED_OFF_KEY.format(plugin_id=PLUGIN_ID)
    try:
        await (_redis.srem(key, rule_id) if body.enabled else _redis.sadd(key, rule_id))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} switched {rule_id} {'on' if body.enabled else 'off'}", flush=True)
    return _rule_dict(plugin, rule, switch)
