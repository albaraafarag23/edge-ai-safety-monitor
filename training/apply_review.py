"""Apply hand-checked labels to a smoking-act dataset (and its re-cut copies).

    python training/apply_review.py reviewed.json data/smoking_act2 data/smoking_act2_384

reviewed.json: [{"crop": "<split>/<label>/<file>", "review": "smoking" | "holding" | "not_smoking" | "drop"}, ...].
Relabelled crops move to their new label folder; dropped ones move to <data>/dropped/. The manifest keeps every
row, with the old label in "label_before_review" and "reviewed" set to yes.
"""
import csv
import json
import shutil
import sys
from pathlib import Path


def main():
    reviews = {r["crop"]: r["review"] for r in json.load(open(sys.argv[1]))}
    for data in map(Path, sys.argv[2:]):
        rows = list(csv.DictReader(open(data / "manifest.csv")))
        changed = 0
        for r in rows:
            new = reviews.get(r["crop"])
            if new is None:
                continue
            r["reviewed"] = "yes"
            if new == r["label"]:
                continue
            dst = Path("dropped") / Path(r["crop"]).name if new == "drop" else Path(r["split"]) / new / Path(r["crop"]).name
            (data / dst).parent.mkdir(parents=True, exist_ok=True)
            if (data / r["crop"]).exists():
                shutil.move(str(data / r["crop"]), str(data / dst))
            r.update(label_before_review=r["label"], label=new, crop=str(dst))
            changed += 1
        cols = list(rows[0].keys())
        for c in ("reviewed", "label_before_review"):
            if c not in cols:
                cols.append(c)
        with open(data / "manifest.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"{data}: {sum(1 for r in rows if r.get('reviewed') == 'yes')} reviewed, {changed} changed")


if __name__ == "__main__":
    main()
