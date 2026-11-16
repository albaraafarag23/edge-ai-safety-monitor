"""People the cameras should recognise (admins only): names and face photos for face recognition.

Photos are files in FACES_DIR, one folder per person, shared with the detector (cv_pipeline/faces.py), which
reads them, picks up changes within seconds and reports through Redis how each photo did:
  faces:photos   hash "<person_id>/<file>" -> {"ok", "problem", "face_px"}
  faces:state    {"engine", "people", "photos", "updated_at"}, expires when the detector stops
There is no database table: the folder is the whole truth, so photos can also be copied in by hand.
Face photos are personal data: they are served to admins only and never leave this machine.
"""
import asyncio
import json
import os
import re
import secrets
import shutil
import time
import unicodedata
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import auth
import confirm
import box_events
from models import User

FACES_DIR = Path(os.getenv("FACES_DIR", "/faces")).resolve()
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTOS = 20
MAX_PEOPLE = 200
# what a photo file starts with -> its extension
IMAGE_STARTS = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"RIFF": ".webp"}
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")

router = APIRouter(prefix="/people", tags=["people"], dependencies=[Depends(auth.require_manager)])
_redis: aioredis.Redis | None = None


def init(redis_url: str):
    global _redis
    _redis = aioredis.from_url(redis_url, decode_responses=True)


async def close():
    if _redis:
        await _redis.aclose()


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    name_ar: str | None = Field(None, max_length=100)


class PersonPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    name_ar: str | None = Field(None, max_length=100)


def _inside(*parts: str) -> Path:
    """A path under FACES_DIR built from request values, or 404: names can't climb out of the folder."""
    if not all(SAFE_NAME.match(p) and ".." not in p for p in parts):
        raise HTTPException(status_code=404, detail="Not found")
    path = FACES_DIR.joinpath(*parts).resolve()
    if not path.is_relative_to(FACES_DIR):
        raise HTTPException(status_code=404, detail="Not found")
    return path


def _person_dir(person_id: str) -> Path:
    folder = _inside(person_id)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Person not found")
    return folder


def _slug(name: str) -> str:
    """A folder name from a person's name: "Omar Ahmed" -> "omar-ahmed"; a name without Latin letters gets a code."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40] or f"person-{secrets.token_hex(3)}"
    candidate, n = slug, 2
    while (FACES_DIR / candidate).exists():
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def _names(folder: Path) -> dict:
    try:
        meta = json.loads((folder / "person.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    meta = meta if isinstance(meta, dict) else {}
    return {"name": str(meta.get("name") or "").strip() or folder.name.replace("_", " ").replace("-", " ").title(),
            "name_ar": str(meta.get("name_ar") or "").strip() or None}


def _write_names(folder: Path, name: str, name_ar: str | None):
    tmp = folder / ".person.json.part"
    tmp.write_text(json.dumps({"name": name.strip(), "name_ar": (name_ar or "").strip() or None}, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, folder / "person.json")


def _photo_files(folder: Path) -> list[Path]:
    return sorted(f for f in folder.iterdir() if f.suffix.lower() in IMAGE_TYPES and not f.name.startswith("."))


def _scan() -> list[tuple[Path, dict, list[Path]]]:
    if not FACES_DIR.is_dir():
        return []
    folders = sorted((p for p in FACES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")),
                     key=lambda p: p.name.lower())
    return [(folder, _names(folder), _photo_files(folder)) for folder in folders]


def _person(folder: Path, names: dict, files: list[Path], results: dict) -> dict:
    photos = []
    for f in files:
        try:
            result = json.loads(results.get(f"{folder.name}/{f.name}", "null"))
        except ValueError:
            result = None
        # checked = the detector has looked at it; until then it is neither good nor bad
        photos.append({"file": f.name, "checked": result is not None, "ok": bool(result and result.get("ok")),
                       "problem": (result or {}).get("problem"), "face_px": (result or {}).get("face_px")})
    return {"person_id": folder.name, **names, "photos": photos, "usable": sum(1 for p in photos if p["ok"])}


async def _results() -> tuple[dict, dict | None]:
    try:
        results = await _redis.hgetall("faces:photos")
        state = await _redis.get("faces:state")
        return results, json.loads(state) if state else None
    except Exception:
        return {}, None


@router.get("")
async def list_people():
    scanned = await asyncio.to_thread(_scan)
    results, state = await _results()
    return {
        # running: the detector is up with face recognition on, so new photos get checked within seconds
        "recognition": {"running": state is not None, **(state or {})},
        "people": [_person(folder, names, files, results) for folder, names, files in scanned],
        "limits": {"photos_per_person": MAX_PHOTOS, "photo_mb": MAX_PHOTO_BYTES // (1024 * 1024)},
    }


@router.post("", status_code=201)
async def add_person(body: PersonIn, me: User = Depends(auth.current_user), _: None = Depends(confirm.required)):
    def create():
        FACES_DIR.mkdir(parents=True, exist_ok=True)
        if sum(1 for p in FACES_DIR.iterdir() if p.is_dir()) >= MAX_PEOPLE:
            raise HTTPException(status_code=409, detail=f"At most {MAX_PEOPLE} people")
        folder = FACES_DIR / _slug(body.name)
        folder.mkdir()
        _write_names(folder, body.name, body.name_ar)
        return folder
    try:
        folder = await asyncio.to_thread(create)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Couldn't write to the faces folder: {e.strerror}")
    print(f"[Backend] {me.name} added person {folder.name}", flush=True)
    await box_events.note("face_photos", f"{me.name} added someone to face recognition.", me.name)
    return _person(folder, _names(folder), [], {})


@router.patch("/{person_id}")
async def rename_person(person_id: str, body: PersonPatch, _: None = Depends(confirm.required)):
    folder = _person_dir(person_id)
    names = _names(folder)
    sent = body.model_fields_set
    _write_names(folder, body.name if "name" in sent and body.name else names["name"],
                 body.name_ar if "name_ar" in sent else names["name_ar"])
    results, _ = await _results()
    return _person(folder, _names(folder), _photo_files(folder), results)


@router.delete("/{person_id}", status_code=204)
async def remove_person(person_id: str, me: User = Depends(auth.current_user), _: None = Depends(confirm.required)):
    """Deletes the person and their photos. The cameras stop recognising them within seconds."""
    await asyncio.to_thread(shutil.rmtree, _person_dir(person_id))
    print(f"[Backend] {me.name} removed person {person_id} and their photos", flush=True)
    await box_events.note("face_photos", f"{me.name} removed someone from face recognition, with their photos.",
                          me.name)


@router.post("/{person_id}/photos", status_code=201)
async def add_photo(person_id: str, request: Request, _: None = Depends(confirm.required)):
    """The request body is the image itself (JPEG, PNG or WebP), not a form."""
    folder = _person_dir(person_id)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail=f"Photos can be up to {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail=f"Photos can be up to {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    extension = next((ext for start, ext in IMAGE_STARTS.items() if data.startswith(start)), None)
    if extension == ".webp" and data[8:12] != b"WEBP":
        extension = None
    if not extension:
        raise HTTPException(status_code=415, detail="Photos must be JPEG, PNG or WebP")
    if len(_photo_files(folder)) >= MAX_PHOTOS:
        raise HTTPException(status_code=409, detail=f"At most {MAX_PHOTOS} photos per person")
    name = f"{int(time.time())}-{secrets.token_hex(4)}{extension}"
    tmp = folder / f".part-{name}"     # the detector skips dot files, so it never reads half a photo
    try:
        await asyncio.to_thread(tmp.write_bytes, bytes(data))
        os.replace(tmp, folder / name)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Couldn't write to the faces folder: {e.strerror}")
    return {"file": name, "checked": False, "ok": False, "problem": None, "face_px": None}


@router.get("/{person_id}/photos/{file}")
async def get_photo(person_id: str, file: str):
    path = _inside(person_id, file)
    if path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{person_id}/photos/{file}", status_code=204)
async def remove_photo(person_id: str, file: str, _: None = Depends(confirm.required)):
    path = _inside(person_id, file)
    if path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    path.unlink()
