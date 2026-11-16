"""Gives a trained model's classes our own names (a dataset's "Fall-Detected" -> "person_down"), so snapshots,
the console and the plugin use one plain word. The weights are unchanged.

    python training/rename_classes.py IN.pt OUT.pt Fall-Detected=person_down
"""
import sys

import torch


def main():
    src, dst, *pairs = sys.argv[1:]
    mapping = dict(p.split("=", 1) for p in pairs)
    ckpt = torch.load(src, map_location="cpu", weights_only=False)
    for holder in (ckpt.get("model"), ckpt.get("ema")):
        if holder is not None and hasattr(holder, "names"):
            holder.names = {i: mapping.get(n, n) for i, n in dict(holder.names).items()}
    torch.save(ckpt, dst)
    print({i: n for i, n in ckpt["model"].names.items()})


if __name__ == "__main__":
    main()
