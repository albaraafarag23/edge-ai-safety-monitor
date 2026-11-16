#!/usr/bin/env python3
"""Prepares a SiteSentry rule drive: a flash drive that carries one rule set (plugin), signed and tied to that
drive (docs/plugin-drives.md). Needs `pip install cryptography`.

    scripts/plugin-drive.py keygen                       once per team: makes the signing key
    scripts/plugin-drive.py make hospital_safety /media/you/STICK
    scripts/plugin-drive.py check /media/you/STICK       what the box will say about this drive

The private key stays on the machine that prepares drives (~/.config/sitesentry/plugin-signing.pem); only the
public half (config/plugin_keys/*.pub) goes to the boxes. Whoever has the private key can make drives every box
accepts, so keep it off shared machines and out of git.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugin_loader"))
import pack  # noqa: E402

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

KEY_FILE = Path(os.getenv("SITESENTRY_SIGNING_KEY") or Path.home() / ".config/sitesentry/plugin-signing.pem")
PUBLIC_DIR = ROOT / "config" / "plugin_keys"


def keygen(args):
    if KEY_FILE.exists():
        raise SystemExit(f"There is already a signing key at {KEY_FILE}. Drives signed with it would stop working "
                         f"if it were replaced; move it away yourself if that is what you want.")
    key = Ed25519PrivateKey.generate()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.touch(mode=0o600)
    KEY_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    public = PUBLIC_DIR / f"{args.name}.pub"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo))
    print(f"Signing key: {KEY_FILE} (keep it private, back it up)\nPublic key for the boxes: {public} (commit it)")


def drive_serial(folder: Path) -> str:
    """The USB serial number of the drive `folder` is on."""
    device = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", str(folder)],
                            capture_output=True, text=True).stdout.strip()
    if not device.startswith("/dev/"):
        raise SystemExit(f"{folder} is not on a drive I can identify (findmnt says: {device or 'nothing'}).")
    disk = subprocess.run(["lsblk", "-n", "-o", "PKNAME", device], capture_output=True, text=True).stdout.strip()
    block = Path("/sys/block") / (disk or Path(device).name)
    path = (block / "device").resolve()
    if "/usb" not in str(path):
        raise SystemExit(f"{folder} is on {device}, which is not a USB drive.")
    for parent in [path, *path.parents]:
        if (parent / "idVendor").is_file():
            serial = (parent / "serial").read_text().strip() if (parent / "serial").is_file() else ""
            if not serial:
                raise SystemExit("This drive has no serial number, so a rule set can't be tied to it. Use another.")
            return serial
    raise SystemExit(f"Couldn't read the serial number of {device}.")


def make(args):
    if not KEY_FILE.is_file():
        raise SystemExit(f"No signing key at {KEY_FILE}. Run: scripts/plugin-drive.py keygen")
    key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
    plugin_path = ROOT / "plugins" / f"{args.plugin_id}.json"
    if not plugin_path.is_file():
        raise SystemExit(f"No plugin {plugin_path}")
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    target = Path(args.drive)
    if not target.is_dir():
        raise SystemExit(f"{target} is not a folder. Give the place the drive is mounted, e.g. /media/you/STICK")
    serial = args.serial or drive_serial(target)

    out = target / pack.FOLDER
    if out.exists():
        shutil.rmtree(out)
    (out / "models").mkdir(parents=True)
    shutil.copyfile(plugin_path, out / "plugin.json")
    models = Path(args.models)
    copied, missing = [], []
    for name in pack.model_files(plugin):
        if not (models / name).is_file():
            missing.append(name)
            continue
        shutil.copyfile(models / name, out / "models" / name)
        copied.append(name)
        # the model's TensorRT build, when there is one: the box then needs no 10-minute conversion
        engine = (Path(args.engines) if args.engines else models) / Path(name).with_suffix(".engine").name
        if engine.is_file():
            shutil.copyfile(engine, out / "models" / engine.name)
            copied.append(engine.name)
    if missing:
        shutil.rmtree(out)
        raise SystemExit(f"These models are not in {models}: {missing}")
    manifest = pack.build_manifest(out, plugin, serial, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (out / "manifest.json").write_bytes(manifest)
    (out / "manifest.sig").write_bytes(pack.sign(manifest, key))
    os.sync()
    print(f"{plugin.get('name', args.plugin_id)} {plugin.get('version', '')} is on {target}\n"
          f"  tied to drive serial …{serial[-4:]}; models: {', '.join(copied)}\n"
          f"  no TensorRT build for: {', '.join(n for n in pack.model_files(plugin) if Path(n).with_suffix('.engine').name not in copied) or 'none'}"
          f"\nUnmount the drive before pulling it out.")


def check(args):
    target = Path(args.drive)
    serial = args.serial or drive_serial(target)
    try:
        manifest, plugin = pack.verify(target / pack.FOLDER, serial, pack.load_public_keys(PUBLIC_DIR))
    except pack.Refused as e:
        raise SystemExit(f"A box would refuse this drive: {e}")
    print(f"A box would accept this drive: {manifest['name']} {manifest['version']} ({manifest['plugin_id']}), "
          f"{len(manifest['files'])} files, tied to serial …{serial[-4:]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    k = sub.add_parser("keygen", help="make the team's signing key (once)")
    k.add_argument("--name", default="team", help="file name of the public key in config/plugin_keys/")
    k.set_defaults(run=keygen)
    m = sub.add_parser("make", help="put a signed rule set on a drive")
    m.add_argument("plugin_id")
    m.add_argument("drive", help="where the drive is mounted")
    m.add_argument("--models", default=str(ROOT / "models"), help="folder with the plugin's model files")
    m.add_argument("--engines", help="folder with TensorRT builds made on the box (default: the models folder)")
    m.add_argument("--serial", help="tie it to this serial instead of reading the drive's (tests)")
    m.set_defaults(run=make)
    c = sub.add_parser("check", help="check a drive the way a box does")
    c.add_argument("drive")
    c.add_argument("--serial", help="check against this serial instead of reading the drive's (tests)")
    c.set_defaults(run=check)
    args = ap.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
