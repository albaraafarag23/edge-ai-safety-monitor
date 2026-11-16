"""Checks for posture.py (lying down, stillness).   python3 test_posture.py"""
from posture import Stillness, is_lying

ok = 0
bad = 0


def check(name, cond):
    global ok, bad
    ok += bool(cond)
    bad += not cond
    print(("PASS " if cond else "FAIL ") + name)


def body(shoulders, hips, knees=None, ankles=None):
    """17 COCO keypoints; only the ones given are visible."""
    kps = [[0, 0, 0.0] for _ in range(17)]
    for (i, j), p in (((5, 6), shoulders), ((11, 12), hips), ((13, 14), knees), ((15, 16), ankles)):
        if p:
            kps[i] = [p[0] - 5, p[1], 0.9]
            kps[j] = [p[0] + 5, p[1], 0.9]
    return kps


standing = body((100, 100), (100, 200), (100, 280), (100, 360))
check("standing upright is not lying", not is_lying([60, 60, 140, 380], standing))
lying = body((100, 300), (220, 305), (300, 308), (380, 310))
check("flat on the ground is lying", is_lying([60, 280, 400, 330], lying))
check("lying, legs hidden, is lying", is_lying([60, 280, 260, 330], body((100, 300), (220, 300))))
bending = body((100, 200), (200, 190), (205, 300), (205, 400))
check("bending over (legs standing under the hips) is not lying", not is_lying([80, 150, 240, 410], bending))
leaning = body((100, 100), (130, 200), (135, 280))
check("leaning a little is not lying", not is_lying([60, 60, 160, 300], leaning))
check("no keypoints, wide box: lying", is_lying([0, 300, 300, 380], [[0, 0, 0.0]] * 17))
check("no keypoints, tall box: not lying", not is_lying([0, 0, 80, 300], [[0, 0, 0.0]] * 17))
check("close-up, hips out of view, wide box: not lying", not is_lying([0, 236, 569, 640], body((100, 600), None)))
ladder = body((150, 75), (285, 120), (240, 210), (255, 290))   # leaning over a ladder (a real false alarm)
check("bending over a ladder is not lying", not is_lying([40, 30, 330, 300], ladder))

s = Stillness()
box = [100, 300, 400, 380]
for t in range(300):                                   # a frame a second; breathing = small shifts
    s.update([[v + (t % 2) * 4 for v in box]], now=t)
still = s.update([[b + 5 for b in box]], now=300)[0]
check("small shifts keep counting stillness (300 s)", abs(still - 300) < 1e-6)
moved = s.update([[b + 120 for b in box]], now=310)[0]
check("rolling over / getting up resets it", moved == 0)
s.update([], now=320)
again = s.update([box], now=330)[0]
check("someone new (or back after a gap) starts at 0", again == 0)
two = s.update([box, [600, 300, 900, 380]], now=331)
check("two people tracked separately", len(two) == 2 and two[1] == 0)

# every plugin must also load in test mode (no models), which the public demo uses when the camera is off
import glob, json
from plugin_config import build_config, test_mode_names
for path in sorted(glob.glob("../plugins/*.json")):
    plugin = json.load(open(path))
    try:
        build_config(plugin, test_mode_names(plugin))
        check(f"test mode loads {plugin['plugin_id']}", True)
    except Exception as e:   # noqa: BLE001
        check(f"test mode loads {plugin['plugin_id']} ({e})", False)

print(f"{ok}/{ok + bad} passed")
raise SystemExit(bad > 0)
