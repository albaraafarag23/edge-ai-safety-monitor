"""Checks of the rule-drive format: what a box accepts and what it refuses. No drive, Redis or root needed.

    cd plugin_loader && python test_pack.py        (needs `pip install cryptography`)
"""
import json
import shutil
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pack

PLUGIN = json.loads((Path(__file__).parent.parent / "plugins" / "hospital_safety.json").read_text())
SERIAL = "AA11BB22CC33"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def make(folder: Path, key, serial=SERIAL, plugin=PLUGIN) -> Path:
    out = folder / pack.FOLDER
    (out / "models").mkdir(parents=True)
    (out / "plugin.json").write_text(json.dumps(plugin))
    for name in pack.model_files(plugin):
        (out / "models" / name).write_bytes(b"weights of " + name.encode())
    manifest = pack.build_manifest(out, plugin, serial, "2026-11-16T12:00:00+00:00")
    (out / "manifest.json").write_bytes(manifest)
    (out / "manifest.sig").write_bytes(pack.sign(manifest, key))
    return out


def reason(out, serial=SERIAL, keys=None):
    try:
        pack.verify(out, serial, [TEAM.public_key()] if keys is None else keys)
        return None
    except pack.Refused as e:
        return e.reason


TEAM, STRANGER = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    good = make(tmp / "good", TEAM)
    manifest, plugin = pack.verify(good, SERIAL, [TEAM.public_key()])
    check("A drive the team signed, plugged in itself, is accepted",
          plugin["plugin_id"] == "hospital_safety" and set(manifest["files"]) == {"plugin.json", "models/medical_ppe.pt", "models/smoking_act3.pt"})
    check("The same files copied to another drive are refused", reason(good, serial="ZZ99") == "wrong_drive")
    check("A drive with no serial number is refused", reason(good, serial="") == "wrong_drive")
    check("A drive signed by someone else is refused", reason(make(tmp / "stranger", STRANGER)) == "unsigned")
    check("A box with no keys accepts nothing", reason(good, keys=[]) == "no_keys")

    edited = make(tmp / "edited", TEAM)
    rules = json.loads((edited / "plugin.json").read_text())
    rules["rules"] = []   # someone switches every rule off after signing
    (edited / "plugin.json").write_text(json.dumps(rules))
    check("Rules changed after signing are refused", reason(edited) == "damaged")

    swapped = make(tmp / "swapped", TEAM)
    (swapped / "models" / "medical_ppe.pt").write_bytes(b"another model, or code")
    check("A model swapped after signing is refused", reason(swapped) == "damaged")

    resigned = make(tmp / "resigned", TEAM)
    m = json.loads((resigned / "manifest.json").read_text())
    m["drive_serial"] = "ZZ99"   # a copier edits the manifest to name their own drive
    (resigned / "manifest.json").write_text(json.dumps(m))
    check("A manifest edited to name another drive is refused (the signature no longer fits)",
          reason(resigned, serial="ZZ99") == "unsigned")

    nosig = make(tmp / "nosig", TEAM)
    (nosig / "manifest.sig").unlink()
    check("A drive without a signature is refused", reason(nosig) == "unsigned")

    short = make(tmp / "short", TEAM)
    (short / "models" / "smoking_act3.pt").unlink()
    check("A drive missing a signed file is refused", reason(short) == "damaged")

    lean = {**PLUGIN, "detection": {**PLUGIN["detection"], "extra_models": []}}
    out = tmp / "lean" / pack.FOLDER
    (out / "models").mkdir(parents=True)
    (out / "plugin.json").write_text(json.dumps(PLUGIN))    # the plugin still wants smoking_act3.pt
    (out / "models" / "medical_ppe.pt").write_bytes(b"x")
    manifest = pack.build_manifest(out, PLUGIN, SERIAL, "now")
    (out / "manifest.json").write_bytes(manifest)
    (out / "manifest.sig").write_bytes(pack.sign(manifest, TEAM))
    check("A signed drive that lacks a model its plugin needs is refused", reason(out) == "damaged")

    sneaky = make(tmp / "sneaky", TEAM)
    m = json.loads((sneaky / "manifest.json").read_text())
    m["files"]["../../etc/passwd"] = "0" * 64
    data = json.dumps(m).encode()
    (sneaky / "manifest.json").write_bytes(data)
    (sneaky / "manifest.sig").write_bytes(pack.sign(data, TEAM))
    check("Even a signed manifest can't name files outside the rule set", reason(sneaky) == "damaged")

    extra = make(tmp / "extra", TEAM)
    (extra / "models" / "unlisted.pt").write_bytes(b"not signed")
    manifest, _ = pack.verify(extra, SERIAL, [TEAM.public_key()])
    check("A file on the drive that the manifest doesn't list is never used", "models/unlisted.pt" not in manifest["files"])

    future = make(tmp / "future", TEAM)
    m = json.loads((future / "manifest.json").read_text())
    m["format"] = 2
    data = json.dumps(m).encode()
    (future / "manifest.json").write_bytes(data)
    (future / "manifest.sig").write_bytes(pack.sign(data, TEAM))
    check("A newer pack format is refused with its own reason", reason(future) == "too_new")
    shutil.rmtree(tmp / "good")

print(f"\n{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
