"""Watches the box's USB ports for a SiteSentry rule drive (docs/plugin-drives.md).

Drive in: mount it read-only, check the rule set on it (pack.py: signed by a key this box trusts, made for this
very drive, every file as signed), copy it into the slot the other services read, unmount, and say "active".
Drive out: empty the slot and say "none"; the services go back to the base plugin (no rules).
A drive that isn't accepted is left alone and the console says why. A drive with no rule set on it is ignored.

The rule set is copied off the drive before it is used, so pulling the drive out can never crash the box.
Runs privileged (it mounts drives). It trusts nothing on a drive until the signature has been checked, and
mounts with noexec/nosuid/nodev.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

import pack
from plugin_source import SLOT_DIR, STATUS_KEY

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
KEYS_DIR = Path(os.getenv("PLUGIN_KEYS_DIR", "/keys"))
MOUNT_DIR = Path(os.getenv("DRIVE_MOUNT_DIR", "/mnt/drive"))
POLL_S = float(os.getenv("DRIVE_POLL_S", "1.5"))
SYS_BLOCK = Path("/sys/block")
# Tests only: a folder that stands in for a plugged-in drive (its serial is DRIVE_TEST_SERIAL). Never set on a box.
TEST_DIR = os.getenv("DRIVE_TEST_DIR")
TEST_SERIAL = os.getenv("DRIVE_TEST_SERIAL", "")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------- finding drives ----------

def usb_serial(block: Path) -> str | None:
    """The serial number of the USB device a disk sits on, from sysfs (None when it isn't a USB disk)."""
    try:
        path = (block / "device").resolve()
    except OSError:
        return None
    if "/usb" not in str(path):
        return None
    for folder in [path, *path.parents]:
        if (folder / "idVendor").is_file():
            try:
                return (folder / "serial").read_text().strip() or None
            except OSError:
                return None
    return None


def usb_partitions() -> list[dict]:
    """[{"device": "/dev/sda1", "serial": "..."}] for every partition (or whole disk without one) on USB."""
    found = []
    for block in sorted(SYS_BLOCK.glob("sd*")):
        serial = usb_serial(block)
        if serial is None:
            continue
        parts = sorted(p.name for p in block.iterdir() if p.name.startswith(block.name) and (p / "partition").is_file())
        for name in parts or [block.name]:
            found.append({"device": f"/dev/{name}", "serial": serial})
    return found


def label_of(device: str) -> str:
    result = subprocess.run(["blkid", "-o", "value", "-s", "LABEL", device], capture_output=True, text=True)
    return result.stdout.strip()[:40]


def mount(device: str) -> bool:
    MOUNT_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["mount", "-o", "ro,nosuid,nodev,noexec", device, str(MOUNT_DIR)],
                            capture_output=True, text=True)
    if result.returncode:
        print(f"[Loader] {device} can't be mounted: {result.stderr.strip()[:160]}", flush=True)
    return result.returncode == 0


def unmount():
    subprocess.run(["umount", str(MOUNT_DIR)], capture_output=True)


# ---------- the slot ----------

def clear_slot():
    slot = Path(SLOT_DIR)
    slot.mkdir(parents=True, exist_ok=True)
    for entry in slot.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def fill_slot(source: Path, manifest: dict):
    """Copies the checked files into the slot. Models first and the plugin last, under a temporary name and then
    renamed: a service that looks during the copy sees either no plugin or a complete one."""
    clear_slot()
    slot = Path(SLOT_DIR)
    (slot / "models").mkdir()
    for name in manifest["files"]:
        if name != "plugin.json":
            shutil.copyfile(source / name, slot / name)
    for name, expected in manifest["files"].items():   # the copy is what runs, so the copy is what must match
        if name != "plugin.json" and pack.sha256(slot / name) != expected:
            raise pack.Refused("damaged", f"{name} didn't copy cleanly")
    tmp = slot / ".plugin.part"
    shutil.copyfile(source / "plugin.json", tmp)
    os.chmod(tmp, 0o644)
    for path in (slot / "models").iterdir():
        os.chmod(path, 0o644)
    os.replace(tmp, slot / f"{manifest['plugin_id']}.json")


# ---------- telling the others ----------

class Announcer:
    def __init__(self):
        self.r = redis.from_url(REDIS_URL, decode_responses=True)
        self.value = None

    def say(self, state: str, **more):
        self.value = json.dumps({"state": state, "at": now(), **more}, ensure_ascii=False)
        print(f"[Loader] {state}" + "".join(f" {k}={v}" for k, v in more.items() if k != "drive"), flush=True)
        self.repeat()

    def repeat(self):
        """Redis may have restarted empty: the status is written again on every round."""
        if self.value is None:
            return
        try:
            self.r.set(STATUS_KEY, self.value)
        except redis.exceptions.RedisError as e:
            print(f"[Loader] Redis not reachable ({e}), will say it again", flush=True)


def take(drive: dict, source: Path, keys, announce: Announcer) -> bool:
    """Checks and installs the rule set at `source`. True when it is now live."""
    about = {"drive": {"label": drive.get("label", ""), "serial_end": drive["serial"][-4:]}}
    announce.say("loading", **about)
    try:
        manifest, plugin = pack.verify(source, drive["serial"], keys)
        fill_slot(source, manifest)
    except pack.Refused as e:
        clear_slot()
        announce.say("refused", reason=e.reason, detail=e.detail, **about)
        return False
    except OSError as e:   # pulled out mid-copy, a failing stick
        clear_slot()
        announce.say("refused", reason="unreadable", detail=str(e)[:160], **about)
        return False
    announce.say("active", plugin_id=manifest["plugin_id"], name=manifest.get("name") or plugin.get("name", ""),
                 version=manifest.get("version", ""), **about)
    return True


def present() -> list[dict]:
    if TEST_DIR:
        return [{"device": TEST_DIR, "serial": TEST_SERIAL}] if (Path(TEST_DIR) / pack.FOLDER).is_dir() else []
    return usb_partitions()


def main():
    announce = Announcer()
    print(f"[Loader] Watching for rule drives. Trusted keys: {len(pack.load_public_keys(KEYS_DIR))} in {KEYS_DIR}"
          + (f" (TEST: {TEST_DIR} stands in for a drive)" if TEST_DIR else ""), flush=True)
    unmount()          # left over from a restart
    clear_slot()       # whatever was live before a restart is checked again from the drive
    announce.say("none")
    current = None     # the partition whose rule set is live, or was refused: don't look at it again until it goes
    ignored = set()    # drives with no rule set on them (someone's own stick): not mounted again while they stay in
    while True:
        drives = present()
        devices = {d["device"] for d in drives}
        ignored &= devices
        if current and current not in devices:
            clear_slot()
            announce.say("none")
            current = None
        if current is None:
            for drive in drives:
                if drive["device"] in ignored:
                    continue
                if TEST_DIR:
                    source = Path(TEST_DIR) / pack.FOLDER
                elif mount(drive["device"]):
                    source = MOUNT_DIR / pack.FOLDER
                    drive["label"] = label_of(drive["device"])
                else:
                    continue
                try:
                    if source.is_dir():   # a drive without a rule set on it is none of our business
                        take(drive, source, pack.load_public_keys(KEYS_DIR), announce)
                        current = drive["device"]
                    else:
                        ignored.add(drive["device"])
                finally:
                    if not TEST_DIR:
                        unmount()
                if current:
                    break
        announce.repeat()
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
