"""Live camera view: the detector (cv_pipeline/live_view.py) keeps the latest annotated JPEG and a
status hash per camera in Redis. This module reads them for the dashboard.

Keys (written by cv_pipeline, both expire within seconds when the detector stops):
  cameras                    set of camera ids that have ever published
  camera:<id>:frame          latest annotated JPEG
  camera:<id>:frame_at       when the camera took it (Unix seconds)
  camera:<id>:info           hash: plugin_id, model, mode, fps, width, height, updated_at
"""
import asyncio
import os
import struct
import time

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Path, Response, WebSocket, WebSocketDisconnect

import auth


router = APIRouter(prefix="/cameras", tags=["cameras"])
ws_router = APIRouter(prefix="/cameras", tags=["cameras"])
# pictures on their way to the browser, not yet shown, at most. The view can't run faster than
# LIVE_WINDOW / round trip: 4 lets all 20 a second through at a 0.2 s round trip (Tailscale Funnel ~0.1-0.2 s),
# and as only the newest picture is ever sent, at most 4 can queue on a slow link
LIVE_WINDOW = int(os.getenv("LIVE_WINDOW") or 4)
LIVE_POLL_S = 0.02       # how often the newest picture's time is checked (the detector publishes up to 20 a second)
LIVE_RECHECK_S = 30      # how often an open live view checks that its session is still valid
# camera ids as the detector accepts them (cv_pipeline/main.py); anything else can't be a Redis key of ours
CameraId = Path(pattern=r"^[A-Za-z0-9_-]{1,40}$")
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
        # the detector's own frame size (boxes and zone polygons are in these pixels); older detectors don't send it
        "frame_width": number("frame_width", int),
        "frame_height": number("frame_height", int),
        "updated_at": info.get("updated_at"),
    }


@router.get("")
async def list_cameras():
    ids = sorted(_text(c) for c in await _redis.smembers("cameras"))
    return list(await asyncio.gather(*(camera_info(c) for c in ids)))


@router.get("/{camera_id}")
async def get_camera(camera_id: str = CameraId):
    if not await _redis.sismember("cameras", camera_id):
        raise HTTPException(status_code=404, detail="Unknown camera")
    return await camera_info(camera_id)


@router.get("/{camera_id}/frame")
async def latest_frame(camera_id: str = CameraId):
    """The newest annotated frame as a JPEG (for a still image or a download)."""
    frame, at = await _redis.mget(f"camera:{camera_id}:frame", f"camera:{camera_id}:frame_at")
    if not frame:
        raise HTTPException(status_code=404, detail="Camera is offline")
    headers = {"Cache-Control": "no-store"}
    if at:   # when the camera took it (Unix seconds)
        headers["X-Captured-At"] = at.decode()
    return Response(frame, media_type="image/jpeg", headers=headers)


@ws_router.websocket("/{camera_id}/live")
async def live(ws: WebSocket, camera_id: str = CameraId):
    """The live view, as fast as the browser's connection allows and never behind. Each message is one picture:
    8 bytes with when the camera took it (big-endian float64, Unix seconds), then the JPEG. The browser answers
    every picture it has put on screen; with LIVE_WINDOW pictures unanswered nothing more is sent, so at most
    that many can pile up in the network's buffers. On a slow link it simply gets fewer, always the newest.
    The session is checked again every LIVE_RECHECK_S: a user switched off, or whose password changed, loses
    the view within that time, like every other page."""
    if not auth.same_site(ws.headers):       # another site's page can't open it with the visitor's cookie
        await ws.close(code=1008)
        return
    token = ws.cookies.get(auth.COOKIE_NAME)
    if not await auth.user_from_token(token):
        await ws.close(code=1008)
        return
    await ws.accept()
    key = f"camera:{camera_id}:frame"
    unanswered = 0
    answered = asyncio.Event()

    async def answers():
        nonlocal unanswered
        while True:
            await ws.receive_text()
            unanswered = max(0, unanswered - 1)   # extra answers can't open the window wider
            answered.set()

    reader = asyncio.create_task(answers())
    last = None
    checked = time.monotonic()
    try:
        while not reader.done():
            if time.monotonic() - checked >= LIVE_RECHECK_S:
                checked = time.monotonic()
                if not await auth.user_from_token(token):
                    await ws.close(code=1008)
                    break
            if unanswered >= LIVE_WINDOW:
                answered.clear()
                waiter = asyncio.create_task(answered.wait())
                await asyncio.wait({reader, waiter}, timeout=LIVE_RECHECK_S, return_when=asyncio.FIRST_COMPLETED)
                waiter.cancel()
                continue
            # the small capture-time key first: the picture itself is fetched only when there is a new one
            at = await _redis.get(f"{key}_at")
            if at is not None and at == last:
                await asyncio.sleep(LIVE_POLL_S)
                continue
            frame, at = await _redis.mget(key, f"{key}_at")
            marker = at or frame   # the capture time, or the picture itself from a detector that doesn't send one
            if not frame or marker == last:
                await asyncio.sleep(LIVE_POLL_S)
                continue
            last = marker
            unanswered += 1
            await ws.send_bytes(struct.pack(">d", float(at or 0)) + frame)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        reader.cancel()
