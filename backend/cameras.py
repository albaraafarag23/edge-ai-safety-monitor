"""Live camera view: the detector (cv_pipeline/live_view.py) keeps the latest annotated JPEG and a
status hash per camera in Redis. This module reads them for the dashboard.

Keys (written by cv_pipeline, both expire within seconds when the detector stops):
  cameras                    set of camera ids that have ever published
  camera:<id>:frame          latest annotated JPEG
  camera:<id>:info           hash: plugin_id, model, mode, fps, width, height, updated_at
"""
import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

STREAM_FPS = 10          # the detector publishes at most 10 frames per second
BOUNDARY = "frame"

router = APIRouter(prefix="/cameras", tags=["cameras"])
_redis: aioredis.Redis | None = None


def init(redis_url: str):
    global _redis
    _redis = aioredis.from_url(redis_url)  # binary: frames are raw JPEG bytes


async def close():
    if _redis:
        await _redis.aclose()


def _text(value) -> str | None:
    return value.decode() if isinstance(value, bytes) else value


async def camera_info(camera_id: str) -> dict:
    raw = await _redis.hgetall(f"camera:{camera_id}:info")
    info = {_text(k): _text(v) for k, v in raw.items()}
    has_frame = await _redis.exists(f"camera:{camera_id}:frame")

    def number(key, cast=float):
        try:
            return cast(info[key])
        except (KeyError, ValueError):
            return None

    return {
        "camera_id": camera_id,
        "online": bool(info) and bool(has_frame),
        "plugin_id": info.get("plugin_id"),
        "model": info.get("model"),
        "mode": info.get("mode"),
        "location": info.get("location"),
        "fps": number("fps"),
        "width": number("width", int),
        "height": number("height", int),
        "updated_at": info.get("updated_at"),
    }


@router.get("")
async def list_cameras():
    ids = sorted(_text(c) for c in await _redis.smembers("cameras"))
    return [await camera_info(c) for c in ids]


@router.get("/{camera_id}")
async def get_camera(camera_id: str):
    if not await _redis.sismember("cameras", camera_id):
        raise HTTPException(status_code=404, detail="Unknown camera")
    return await camera_info(camera_id)


@router.get("/{camera_id}/frame")
async def latest_frame(camera_id: str):
    """The newest annotated frame as a JPEG (for a still image or a download)."""
    frame = await _redis.get(f"camera:{camera_id}:frame")
    if not frame:
        raise HTTPException(status_code=404, detail="Camera is offline")
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/stream")
async def stream(camera_id: str, request: Request):
    """Motion JPEG: an <img> pointed here plays the camera live, no player needed."""
    key = f"camera:{camera_id}:frame"

    async def frames():
        last = None
        while not await request.is_disconnected():
            frame = await _redis.get(key)
            if frame and frame != last:
                last = frame
                yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n"
                       .encode() + frame + b"\r\n")
            await asyncio.sleep(1 / STREAM_FPS)

    return StreamingResponse(frames(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
