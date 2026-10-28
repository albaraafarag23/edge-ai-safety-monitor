"""Sort the "unsure" smoking crops (photos labelled smoking with no item box, so mouth or hand is unknown) with a
first model trained on the clean labels.

    python training/sort_unsure.py outputs/runs/smoking_act2_s/weights/best.pt                 # report only
    python training/sort_unsure.py outputs/runs/smoking_act2_s/weights/best.pt --apply         # move into the set

The source says the person smokes, so a crop is only ever smoking or holding:
  - smoking or holding with probability >= --sure: moved into its split (by original photo) and label folder
  - the model says not_smoking above --sure: dropped (the crop probably missed the smoker)
  - anything else: listed in <data>/unsure_review.csv to check by eye
  - --trust-types (default pipe, cigar, shisha): the first model has never seen these items and calls them
    not smoking, so they count as smoking unless it is sure they are holding. Their source photos are of people
    smoking them, nearly always with the item at the mouth (checked by eye on 2026-10-21).
Every decision is written to <data>/unsure_sorted.csv; with --apply the moved crops are added to manifest.csv
(column "sorted_by" names the model).
"""
import argparse
import csv
import shutil
from collections import Counter
from pathlib import Path

from ultralytics import YOLO

from build_smoking_crops import split_of


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights")
    ap.add_argument("--data", type=Path, default=Path("data/smoking_act2"))
    ap.add_argument("--sure", type=float, default=0.8)
    ap.add_argument("--apply", action="store_true", help="move the sure crops into the dataset")
    ap.add_argument("--trust-types", nargs="*", default=["pipe", "cigar", "shisha"])
    args = ap.parse_args()

    manifest = args.data / "manifest.csv"
    rows = list(csv.DictReader(open(manifest)))
    unsure = [r for r in rows if r["label"] == "unsure" and (args.data / r["crop"]).exists()]
    model = YOLO(args.weights)
    names = model.names
    for i in range(0, len(unsure), 64):
        chunk = unsure[i:i + 64]
        for r, p in zip(chunk, model.predict([str(args.data / r["crop"]) for r in chunk], verbose=False)):
            probs = {names[k]: float(v) for k, v in enumerate(p.probs.data.tolist())}
            r.update({f"p_{k}": round(v, 4) for k, v in probs.items()})
            top = max(probs, key=probs.get)
            r["decision"] = ("drop" if top == "not_smoking" else top) if probs[top] >= args.sure else "review"
            if r["type"] in args.trust_types:
                r["decision"] = "holding" if probs.get("holding", 0) >= args.sure else "smoking"

    cols = ["crop", "type", "source", "decision"] + [f"p_{n}" for n in names.values()]
    for name, sel in (("unsure_sorted.csv", unsure), ("unsure_review.csv", [r for r in unsure if r["decision"] == "review"])):
        with open(args.data / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(sel)
    print("decisions:", dict(Counter(r["decision"] for r in unsure)))
    print("by type:", dict(Counter((r["type"], r["decision"]) for r in unsure)))

    if not args.apply:
        print(f"Report only. Details: {args.data / 'unsure_sorted.csv'}. Re-run with --apply to move the sure ones.")
        return
    moved = 0
    for r in unsure:
        if r["decision"] not in ("smoking", "holding"):
            continue
        split = split_of(r["group"])
        dst = Path(split) / r["decision"] / Path(r["crop"]).name
        (args.data / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(args.data / r["crop"]), str(args.data / dst))
        r.update(crop=str(dst), split=split, label=r["decision"], sorted_by=str(args.weights))
        moved += 1
    cols = list(rows[0].keys()) + (["sorted_by"] if "sorted_by" not in rows[0] else [])
    with open(manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Moved {moved} crops into the dataset and updated {manifest}.")


if __name__ == "__main__":
    main()
