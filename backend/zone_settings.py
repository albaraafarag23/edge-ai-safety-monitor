"""Zones drawn in the console: an admin or supervisor redraws a plugin zone (e.g. the excavation edge) on the live
camera picture, instead of editing the plugin file once the camera is mounted.

Polygons are stored as fractions of the picture (0-1), so they fit any camera resolution, in Postgres and mirrored
to Redis, where the event engine reads them (with the rule settings, every 2 s):
  zones:settings:<plugin_id>   hash zone_id -> {"polygon": [[x, y], ...]} as JSON
The engine turns them into pixels with each detection's frame_size. Redis isn't persistent, so the hash is rewritten
at startup and every RESYNC_S seconds. Deleting a zone's row goes back to the plugin's polygon.
"""
import asyncio
import json
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

import auth
from models import SessionLocal, User, ZoneSetting, iso
from rule_settings import PLUGIN_ID, load_plugin

ZONES_KEY = "zones:settings:{plugin_id}"
RESYNC_S = 30

router = APIRouter(prefix="/zones", tags=["zones"])
_redis: aioredis.Redis | None = None


class ZoneDrawing(BaseModel):
    polygon: list[list[float]] = Field(min_length=3, max_length=24)

    @field_validator("polygon")
    @classmethod
    def inside_picture(cls, polygon):
        if any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in polygon):
            raise ValueError("each point is [x, y] with both between 0 and 1 (fractions of the picture)")
        return [[round(x, 4), round(y, 4)] for x, y in polygon]


def _zone_dict(zone_id: str, zone: dict, plugin: dict, row: ZoneSetting | None) -> dict:
    return {
        "zone_id": zone_id,
        "name": zone.get("name", zone_id),
        "camera_id": zone.get("camera_id"),
        "plugin_polygon": zone.get("polygon", []),   # pixels of the camera's frame (the camera reports frame_width/height)
        "polygon": row.polygon if row else None,     # redrawn in the console, fractions of the picture
        "rules": [{"rule_id": r["rule_id"], "name": r.get("name") or r["rule_id"]}
                  for r in plugin.get("rules", []) if r.get("zone") == zone_id],
        "changed_by": row.changed_by if row else None,
        "changed_at": iso(row.changed_at) if row else None,
    }


async def _rows() -> dict[str, ZoneSetting]:
    async with SessionLocal() as session:
        rows = (await session.scalars(select(ZoneSetting).where(ZoneSetting.plugin_id == PLUGIN_ID))).all()
    return {row.zone_id: row for row in rows}


async def sync_redis():
    rows = await _rows()
    key = ZONES_KEY.format(plugin_id=PLUGIN_ID)
    async with _redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if rows:
            pipe.hset(key, mapping={zid: json.dumps({"polygon": row.polygon}) for zid, row in rows.items()})
        await pipe.execute()


async def keep_synced(redis_url: str):
    """Runs for the backend's lifetime, so a Redis restart doesn't quietly undo the drawn zones."""
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            await sync_redis()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Backend] Couldn't sync zones to Redis: {e}", flush=True)
        await asyncio.sleep(RESYNC_S)


async def close():
    if _redis:
        await _redis.aclose()


def _plugin_zone(zone_id: str) -> tuple[dict, dict]:
    plugin = load_plugin()
    zone = (plugin or {}).get("zones", {}).get(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return plugin, zone


@router.get("")
async def list_zones():
    plugin = load_plugin()
    if not plugin:
        raise HTTPException(status_code=503, detail="Plugin not found")
    rows = await _rows()
    return [_zone_dict(zid, z, plugin, rows.get(zid)) for zid, z in plugin.get("zones", {}).items()]


@router.put("/{zone_id}")
async def draw_zone(zone_id: str, body: ZoneDrawing, me: User = Depends(auth.can_handle_incidents)):
    plugin, zone = _plugin_zone(zone_id)
    async with SessionLocal() as session:
        row = await session.get(ZoneSetting, (PLUGIN_ID, zone_id))
        if not row:
            row = ZoneSetting(plugin_id=PLUGIN_ID, zone_id=zone_id)
            session.add(row)
        row.polygon = body.polygon
        row.changed_by = me.name
        row.changed_at = datetime.utcnow()
        await session.commit()
    try:
        await _redis.hset(ZONES_KEY.format(plugin_id=PLUGIN_ID), zone_id, json.dumps({"polygon": row.polygon}))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} redrew zone {zone_id} ({len(row.polygon)} points)", flush=True)
    return _zone_dict(zone_id, zone, plugin, row)


@router.delete("/{zone_id}")
async def reset_zone(zone_id: str, me: User = Depends(auth.can_handle_incidents)):
    """Back to the plugin's own polygon."""
    plugin, zone = _plugin_zone(zone_id)
    async with SessionLocal() as session:
        row = await session.get(ZoneSetting, (PLUGIN_ID, zone_id))
        if row:
            await session.delete(row)
            await session.commit()
    try:
        await _redis.hdel(ZONES_KEY.format(plugin_id=PLUGIN_ID), zone_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} reset zone {zone_id} to the plugin's polygon", flush=True)
    return _zone_dict(zone_id, zone, plugin, None)
