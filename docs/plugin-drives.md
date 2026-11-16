# Rule drives: the rules on a USB flash drive

A SiteSentry box can ship with **no rules**. Each rule set (plugin: construction, hospital, ...) is sold on its own
USB flash drive. Plug the drive in and within a few seconds the box runs its rules; pull it out and the box goes
back to watching with no rules.

| Drive | What the box does |
|---|---|
| none | Live picture, people boxed and recognised by face, history, reports and analytics all available. No rule is checked, no incident is raised. The console says "No rule drive plugged in". |
| a SiteSentry rule drive | Its rules, zones, recommended actions and models run. The console's Safety rules page, sidebar and incident wording are that plugin's. |
| a drive that isn't accepted | Nothing changes; the console says why (not signed, made for another drive, changed after signing, ...). |
| any other USB stick | Ignored. |

Rule settings changed in the console (switches, durations, working hours) and drawn zones are kept per plugin,
so taking the hospital drive out and putting it back brings its settings back. Past incidents stay whatever is
plugged in.

## Why a copied drive doesn't work

Every drive is signed with the team's private key, and the signature covers:
- the drive's own USB serial number, so the same files copied to another stick are refused;
- a SHA-256 hash of every file, so changed rules or a swapped model are refused;
- the plugin id, version and file list, so nothing can be added under a signed name.

The box only holds the public half of the key (`config/plugin_keys/*.pub`), so a box can check drives but can't
make them. The private key never leaves the machine that prepares drives. Anyone who has it can make drives that
every box accepts: keep it off shared machines, back it up somewhere safe, and never commit it.

A drive is mounted read-only with `noexec,nosuid,nodev`, nothing on it is believed before the signature is
checked, and the checked files are copied into the box before anything uses them, so pulling the drive out in
the middle can't crash anything.

Limits, plainly: a drive's serial number can be read by anyone, and some cheap drives can have it rewritten, so
this stops copying by ordinary users, not a determined attacker with the hardware. A drive without a serial
number can't be used.

## Making a drive

Once per team, on the machine that will prepare drives:

    pip install cryptography
    scripts/plugin-drive.py keygen          # private key: ~/.config/sitesentry/plugin-signing.pem
                                            # public key: config/plugin_keys/team.pub (commit it, deploy it)

For each drive (FAT32 or ext4; plug it in, the desktop mounts it, e.g. at /media/you/STICK):

    scripts/plugin-drive.py make hospital_safety /media/you/STICK
    scripts/plugin-drive.py check /media/you/STICK     # what a box will say about it
    # eject it before pulling it out

`make` puts the plugin and every model it names on the drive, ties it to that drive's serial and signs it. Add
`--engines <folder>` to include the models' TensorRT builds made on a Jetson (see below).

## Running a box from drives

In the box's `.env`:

    PLUGIN_SOURCE=drive
    COMPOSE_PROFILES=drives        # starts plugin_loader, the service that watches the USB ports

and put the team's public key in `config/plugin_keys/`. `plugins/` on a box sold this way needs only
`base.json` (the no-rules plugin); the others may stay for development.

`PLUGIN_SOURCE=fixed` (the default) is the old behaviour: the plugin named by `PLUGIN_ID` always runs, and
plugged-in drives are ignored.

### How the switch happens
1. `plugin_loader` sees a new USB partition, mounts it read-only and looks for `sitesentry-plugin/`.
2. It checks the signature, the drive serial and every file's hash, copies the files into the shared
   `plugin_slot` volume (plugin last, renamed into place), and writes `site:plugin` in Redis
   (`{"state": "active", "plugin_id", "name", "version"}`; or `"refused"` with a reason).
3. The detector sees the new plugin within a second and restarts itself to load its models; the rule engine
   loads the plugins again; the backend copies that plugin's rule settings and zones to Redis and tells the
   console over the live stream.
4. When the drive is removed, the slot is emptied and `site:plugin` says `"none"`; everything goes back to
   `plugins/base.json`.

Measured on a laptop with a folder standing in for the drive (`DRIVE_TEST_DIR`, tests only), 2026-11-16:
accepted in 2 s, detector running the drive's models 3-10 s later; removed: no rules after 2 s, detector back
on the base model 6 s later. A tampered drive was refused and nothing was copied.

### Models on the Jetson
A `.pt` model runs on the Jetson but slowly. For full speed the drive should carry the model's TensorRT build,
which is tied to the type of device: build it once on a Jetson (`jetson/README.md`, "TensorRT models"), copy the
`.engine` back, and make the drive with `--engines <folder with it>`. The detector uses `<model>.engine` from the
drive when it is there and the `.pt` otherwise.

Not yet measured on the Jetson with a real drive: mounting (the host kernel must have the drive's filesystem;
FAT32 is safe), and the time to switch with TensorRT builds.

## Files
- `plugin_loader/main.py` the USB watcher; `pack.py` the drive format and its checks; `test_pack.py` (14 checks).
- `plugin_loader/plugin_source.py` which plugin is live, copied into each service (`scripts/check-all.sh`
  checks the copies are identical).
- `scripts/plugin-drive.py` keygen / make / check.
- `plugins/base.json` the no-rules plugin (general person model `yolo11n.pt`).
