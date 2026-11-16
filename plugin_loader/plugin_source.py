"""Which rule set (plugin) is live, for every service. The same file is copied into cv_pipeline/, event_engine/,
backend/ and ai_reporting/ (scripts/check-all.sh checks the copies are identical); edit it here.

Two ways to run (PLUGIN_SOURCE):
  fixed  (default) the plugin named by PLUGIN_ID, from PLUGINS_DIR. Development, tests, a site that never changes.
  drive  the box ships with no rules. A rule set arrives on a signed flash drive: plugin_loader/ checks it, copies
         it into the slot (PLUGIN_SLOT_DIR) and says so in Redis (`site:plugin`). While a drive is in, its plugin is
         live; with none, the base plugin runs (people are still seen, nothing is checked). docs/plugin-drives.md.
"""
import json
import os
from pathlib import Path

SOURCE = (os.getenv("PLUGIN_SOURCE") or "fixed").lower()          # fixed | drive
FIXED_ID = os.getenv("PLUGIN_ID") or "construction_safety"
BASE_ID = os.getenv("BASE_PLUGIN_ID") or "base"                   # what runs with no drive in
PLUGINS_DIR = os.getenv("PLUGINS_DIR") or "./plugins"
SLOT_DIR = os.getenv("PLUGIN_SLOT_DIR") or "/plugin_slot"         # the checked copy of what is on the drive
STATUS_KEY = "site:plugin"
# Redis value (JSON), written by plugin_loader:
#   {"state": "none" | "loading" | "active" | "refused", "plugin_id", "name", "version", "reason", "drive", "at"}


def status(raw: str | bytes | None) -> dict:
    """The loader's last word, or {} when it has said nothing (yet)."""
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def active_id(raw: str | bytes | None = None) -> str:
    """The plugin to run now. `raw` is the Redis value of STATUS_KEY (only looked at in drive mode)."""
    if SOURCE != "drive":
        return FIXED_ID
    s = status(raw)
    return str(s["plugin_id"]) if s.get("state") == "active" and s.get("plugin_id") else BASE_ID


def from_drive(plugin_id: str) -> bool:
    return SOURCE == "drive" and plugin_id != BASE_ID


def models_dir(plugin_id: str, default: str) -> str:
    """A drive's plugin brings its own models; everything else uses the box's."""
    return str(Path(SLOT_DIR) / "models") if from_drive(plugin_id) else default


def load_all() -> dict:
    """Every plugin a service may meet: the built-in ones and, in drive mode, the one in the slot (it wins)."""
    folders = [PLUGINS_DIR] + ([SLOT_DIR] if SOURCE == "drive" else [])
    plugins = {}
    for folder in folders:
        for path in sorted(Path(folder).glob("*.json")):
            if path.name == "state.json":
                continue
            try:
                plugin = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue   # half-written during a swap, or not a plugin: the next look gets it
            if isinstance(plugin, dict) and plugin.get("plugin_id"):
                plugins[plugin["plugin_id"]] = plugin
    return plugins


def load(plugin_id: str) -> dict | None:
    return load_all().get(plugin_id)
