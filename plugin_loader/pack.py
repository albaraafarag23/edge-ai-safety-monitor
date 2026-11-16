"""A rule set on a flash drive: how it is laid out, signed and checked. Used by the loader on the box
(main.py) and by the tool that prepares a drive (scripts/plugin-drive.py). docs/plugin-drives.md.

On the drive:
    sitesentry-plugin/
        manifest.json    {"format": 1, "plugin_id", "name", "version", "drive_serial", "created_at",
                          "files": {"plugin.json": "<sha256>", "models/x.pt": "<sha256>", ...}}
        manifest.sig     Ed25519 signature of manifest.json's bytes, base64
        plugin.json      the plugin (docs/plugins.md)
        models/          every model file the plugin names, and their TensorRT builds where there are any

The signature covers the manifest, the manifest lists every file's hash and the drive's own serial number. So a
changed file, a file from somewhere else, or the same files copied to another drive are all refused.
"""
import base64
import hashlib
import json
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

FOLDER = "sitesentry-plugin"
FORMAT = 1
PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
FILE_NAME = re.compile(r"^(plugin\.json|models/[A-Za-z0-9][A-Za-z0-9._-]{0,80})$")
MAX_PACK_BYTES = 2 * 1024 ** 3
MODEL_SUFFIXES = (".pt", ".engine", ".onnx")


class Refused(Exception):
    """Why a drive is not accepted. `reason` is a short code the console turns into a sentence."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def model_files(plugin: dict) -> list[str]:
    """The model file names a plugin runs (main model and extra models)."""
    detection = plugin.get("detection") or {}
    return [m["model"] for m in [detection, *(detection.get("extra_models") or [])] if m.get("model")]


def load_public_keys(folder: Path) -> list[Ed25519PublicKey]:
    keys = []
    for path in sorted(Path(folder).glob("*.pub")):
        try:
            key = serialization.load_pem_public_key(path.read_bytes())
        except ValueError:
            continue
        if isinstance(key, Ed25519PublicKey):
            keys.append(key)
    return keys


def sign(manifest_bytes: bytes, private_key: Ed25519PrivateKey) -> bytes:
    return base64.b64encode(private_key.sign(manifest_bytes))


def verify(pack: Path, drive_serial: str, keys: list[Ed25519PublicKey]) -> tuple[dict, dict]:
    """(manifest, plugin) of a pack that may be run on this drive, or raises Refused.

    Order matters: nothing in the pack is believed before the signature has been checked."""
    manifest_path, signature_path = pack / "manifest.json", pack / "manifest.sig"
    if not manifest_path.is_file() or not signature_path.is_file():
        raise Refused("unsigned", "no manifest or no signature on the drive")
    manifest_bytes = manifest_path.read_bytes()
    if len(manifest_bytes) > 1 << 20:
        raise Refused("damaged", "manifest too large")
    try:
        signature = base64.b64decode(signature_path.read_bytes().strip(), validate=True)
    except ValueError:
        raise Refused("unsigned", "the signature can't be read")
    if not keys:
        raise Refused("no_keys", "this box has no key to check drives with")
    for key in keys:
        try:
            key.verify(signature, manifest_bytes)
            break
        except InvalidSignature:
            continue
    else:
        raise Refused("unsigned", "the signature is not from a key this box trusts")

    try:
        manifest = json.loads(manifest_bytes)
        files = manifest["files"]
        plugin_id = manifest["plugin_id"]
    except (ValueError, KeyError, TypeError):
        raise Refused("damaged", "the manifest can't be read")
    if manifest.get("format") != FORMAT:
        raise Refused("too_new", f"pack format {manifest.get('format')}, this box reads format {FORMAT}")
    if not isinstance(files, dict) or not isinstance(plugin_id, str) or not PLUGIN_ID.match(plugin_id):
        raise Refused("damaged", "the manifest is not in the expected form")
    if not drive_serial or manifest.get("drive_serial") != drive_serial:
        raise Refused("wrong_drive", "this rule set was made for another drive")
    if "plugin.json" not in files or any(not isinstance(n, str) or not FILE_NAME.match(n) for n in files):
        raise Refused("damaged", "the manifest lists a file it shouldn't")

    total = 0
    for name, expected in files.items():
        path = pack / name
        if not path.is_file() or path.is_symlink():
            raise Refused("damaged", f"{name} is missing")
        total += path.stat().st_size
        if total > MAX_PACK_BYTES:
            raise Refused("damaged", "the rule set is larger than this box accepts")
        if sha256(path) != expected:
            raise Refused("damaged", f"{name} was changed after signing")
    try:
        plugin = json.loads((pack / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused("damaged", "the plugin can't be read")
    if not isinstance(plugin, dict) or plugin.get("plugin_id") != plugin_id:
        raise Refused("damaged", "the plugin doesn't match its manifest")
    for model in model_files(plugin):
        if f"models/{model}" not in files:
            raise Refused("damaged", f"the plugin needs {model}, which is not in the rule set")
    return manifest, plugin


def build_manifest(pack: Path, plugin: dict, drive_serial: str, created_at: str) -> bytes:
    """The manifest for the files now in `pack` (plugin.json and models/)."""
    names = ["plugin.json"] + sorted(f"models/{p.name}" for p in (pack / "models").iterdir() if p.is_file())
    bad = [n for n in names if not FILE_NAME.match(n)]
    if bad:
        raise ValueError(f"file names a pack can't hold: {bad}")
    manifest = {"format": FORMAT, "plugin_id": plugin["plugin_id"], "name": plugin.get("name", plugin["plugin_id"]),
                "version": str(plugin.get("version", "")), "drive_serial": drive_serial, "created_at": created_at,
                "files": {n: sha256(pack / n) for n in names}}
    return json.dumps(manifest, indent=2, ensure_ascii=False).encode()
