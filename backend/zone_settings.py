"""Zones drawn in the console: an admin or supervisor draws a plugin zone (e.g. the excavation edge) on a camera's
live picture, instead of editing the plugin file once the camera is mounted.

A drawing belongs to one camera: each camera looks at a different part of the site, so the same zone has a
different shape on each (or isn't there at all). The plugin's own polygon applies on the camera the plugin names
(every camera if it names none); on any other camera a zone exists only once it is drawn there.

Polygons are stored as fractions of the picture (0-1), so they fit any camera resolution, in Postgres
(`zone_drawings`) and mirrored to Redis, where the event engine reads them (with the rule settings, every 2 s):
  zones:settings:<plugin_id>   hash "<camera_id>/<zone_id>" -> {"camera_id", "zone_id", "polygon": [[x, y], ...]}
The engine turns them into pixels with each detection's frame_size. The hash is rewritten at startup and every
RESYNC_S seconds, so a Redis restart doesn't lose it. Deleting a drawing goes back to the plugin's polygon.
"""
import asyncio
import json
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text

import auth
from models import SessionLocal, User, ZoneDrawing, iso
from rule_settings import PLUGIN_ID, load_plugin

ZONES_KEY = "zones:settings:{plugin_id}"
RESYNC_S = 30
CAMERA_ID = Query(pattern=r"^[A-Za-z0-9_-]{1,40}$", description="the camera the zone is drawn on")

router = APIRouter(prefix="/zones", tags=["zones"])
_redis: aioredis.Redis | None = None


class ZoneShape(BaseModel):
    polygon: list[list[float]] = Field(min_length=3, max_length=24)

    @field_validator("polygon")
    @classmethod
    def inside_picture(cls, polygon):
        if any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in polygon):
            raise ValueError("each point is [x, y] with both between 0 and 1 (fractions of the picture)")
        return [[round(x, 4), round(y, 4)] for x, y in polygon]


def _field(camera_id: str, zone_id: str) -> str:
    return f"{camera_id}/{zone_id}"


def _value(row: ZoneDrawing) -> str:
    return json.dumps({"camera_id": row.camera_id, "zone_id": row.zone_id, "polygon": row.polygon})


def _zone_dict(zone_id: str, zone: dict, plugin: dict, camera_id: str, row: ZoneDrawing | None) -> dict:
    from_plugin = zone.get("camera_id") in (None, camera_id)
    return {
        "zone_id": zone_id,
        "name": zone.get("name", zone_id),
        "camera_id": zone.get("camera_id"),            # the camera the plugin puts it on (null = every camera)
        # false: this camera doesn't have the zone (yet); drawing it here adds it
        "on_camera": from_plugin or row is not None,
        # the plugin's shape, in pixels of the camera's frame (the camera reports frame_width/height)
        "plugin_polygon": zone.get("polygon", []) if from_plugin else [],
        "polygon": row.polygon if row else None,       # drawn in the console for this camera, fractions of the picture
        "rules": [{"rule_id": r["rule_id"], "name": r.get("name") or r["rule_id"]}
                  for r in plugin.get("rules", []) if r.get("zone") == zone_id],
        "changed_by": row.changed_by if row else None,
        "changed_at": iso(row.changed_at) if row else None,
    }


async def _rows(camera_id: str | None = None) -> list[ZoneDrawing]:
    query = select(ZoneDrawing).where(ZoneDrawing.plugin_id == PLUGIN_ID)
    if camera_id:
        query = query.where(ZoneDrawing.camera_id == camera_id)
    async with SessionLocal() as session:
        return list((await session.scalars(query)).all())


async def import_old_drawings():
    """Zones drawn before drawings were per camera (table zone_settings) move to the camera the plugin names."""
    plugin = load_plugin() or {}
    async with SessionLocal() as session:
        if await session.scalar(select(func.count()).select_from(ZoneDrawing)):
            return
        try:
            old = (await session.execute(text(
                "SELECT zone_id, polygon, changed_by, changed_at FROM zone_settings WHERE plugin_id = :p"),
                {"p": PLUGIN_ID})).all()
        except Exception:   # no such table: a fresh install
            return
        for zone_id, polygon, changed_by, changed_at in old:
            camera_id = (plugin.get("zones", {}).get(zone_id) or {}).get("camera_id") or "cam_01"
            session.add(ZoneDrawing(plugin_id=PLUGIN_ID, camera_id=camera_id, zone_id=zone_id, polygon=polygon,
                                    changed_by=changed_by, changed_at=changed_at))
        await session.commit()
        if old:
            print(f"[Backend] Moved {len(old)} drawn zone(s) to per-camera storage", flush=True)


async def sync_redis():
    rows = await _rows()
    key = ZONES_KEY.format(plugin_id=PLUGIN_ID)
    async with _redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if rows:
            pipe.hset(key, mapping={_field(row.camera_id, row.zone_id): _value(row) for row in rows})
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
async def list_zones(camera_id: str = CAMERA_ID):
    """Every zone of the plugin, as this camera has it."""
    plugin = load_plugin()
    if not plugin:
        raise HTTPException(status_code=503, detail="Plugin not found")
    rows = {row.zone_id: row for row in await _rows(camera_id)}
    return [_zone_dict(zid, z, plugin, camera_id, rows.get(zid)) for zid, z in plugin.get("zones", {}).items()]


@router.put("/{zone_id}")
async def draw_zone(zone_id: str, body: ZoneShape, camera_id: str = CAMERA_ID,
                    me: User = Depends(auth.can_handle_incidents)):
    plugin, zone = _plugin_zone(zone_id)
    async with SessionLocal() as session:
        row = await session.get(ZoneDrawing, (PLUGIN_ID, camera_id, zone_id))
        if not row:
            row = ZoneDrawing(plugin_id=PLUGIN_ID, camera_id=camera_id, zone_id=zone_id)
            session.add(row)
        row.polygon = body.polygon
        row.changed_by = me.name
        row.changed_at = datetime.utcnow()
        await session.commit()
    try:
        await _redis.hset(ZONES_KEY.format(plugin_id=PLUGIN_ID), _field(camera_id, zone_id), _value(row))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} drew zone {zone_id} on {camera_id} ({len(row.polygon)} points)", flush=True)
    return _zone_dict(zone_id, zone, plugin, camera_id, row)


@router.delete("/{zone_id}")
async def reset_zone(zone_id: str, camera_id: str = CAMERA_ID, me: User = Depends(auth.can_handle_incidents)):
    """Back to the plugin's own polygon (on a camera the plugin doesn't put the zone on: the zone goes away)."""
    plugin, zone = _plugin_zone(zone_id)
    async with SessionLocal() as session:
        row = await session.get(ZoneDrawing, (PLUGIN_ID, camera_id, zone_id))
        if row:
            await session.delete(row)
            await session.commit()
    try:
        await _redis.hdel(ZONES_KEY.format(plugin_id=PLUGIN_ID), _field(camera_id, zone_id))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Saved, but the detector couldn't be updated yet: {e}")
    print(f"[Backend] {me.name} removed the drawing of zone {zone_id} on {camera_id}", flush=True)
    return _zone_dict(zone_id, zone, plugin, camera_id, None)
