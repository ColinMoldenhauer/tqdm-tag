"""Short demo workload meant to be recorded with asciinema.

Shows a plain tqdm bar, then a tqdm-tag bar where each item is colored by its
(deterministic) outcome, with a live legend.

Easiest way to record it: ``scripts/record_demo.sh`` (see ``--help``).

Setup (Linux/macOS; on Windows use WSL)
---------------------------------------
    # asciinema: records the terminal session into a .cast file
    sudo apt install -y asciinema            # or: brew install asciinema
    # agg: renders a .cast to a GIF (needs a recent glibc; if the prebuilt
    # binary complains about GLIBC, build it instead: needs Rust/cargo)
    cargo install --git https://github.com/asciinema/agg
    #   ...or download a binary from https://github.com/asciinema/agg/releases
    # the demo itself
    pip install -e .                         # from the repo root (pulls in tqdm, numpy)

Manual recording (what record_demo.sh does)
-------------------------------------------
    stty cols 80 rows 14                     # asciinema 2.x records the current terminal size
    export TERM=xterm-256color LANG=C.UTF-8
    asciinema rec demo.cast --overwrite -c "python scripts/demo_run.py"
    agg --font-size 16 demo.cast docs/assets/demo.gif

``--only plain|tag`` runs just one of the two bars (both then use the same
speed, so two recordings line up for a side-by-side view).
"""
import argparse
import random
import time

from tqdm import tqdm

from tqdm_tag import Tag, TqdmTag

N = 40
PLAIN_DELAY = 0.02  # keep the plain-tqdm part short when shown before tqdm-tag
DELAY = 0.06


def outcomes(n=N, seed=4):
    """Deterministic per-item outcome so every run (and both bars) agree."""
    rng = random.Random(seed)
    return ["error" if (r := rng.random()) < 0.07 else "warn" if r < 0.22 else "ok" for _ in range(n)]


def run_plain(ncols, delay):
    print("# plain tqdm")
    for _ in tqdm(range(N), ncols=ncols):
        time.sleep(delay)


def run_tag(ncols):
    res = outcomes()
    print("# tqdm-tag")
    pbar = TqdmTag(
        range(N),
        tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
        legend=True,
        ncols=ncols,
    )
    for i in pbar:
        time.sleep(DELAY)
        if res[i] != "ok":
            pbar.tag(res[i])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=["plain", "tag"], help="run just one of the two bars")
    ap.add_argument("--ncols", type=int, default=78, help="bar width (keep <= terminal columns)")
    a = ap.parse_args()

    if a.only == "plain":
        run_plain(a.ncols, DELAY)  # same speed as the tag run so GIFs line up
    elif a.only == "tag":
        run_tag(a.ncols)
    else:
        run_plain(a.ncols, PLAIN_DELAY)
        print()
        run_tag(a.ncols)


if __name__ == "__main__":
    main()
