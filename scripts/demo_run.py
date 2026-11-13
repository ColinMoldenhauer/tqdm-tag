"""Short demo workload meant to be recorded with asciinema.

Shows a plain tqdm bar, then a tqdm-tag bar where each item is colored by its
(deterministic) outcome, with a live legend. Record and convert with:

    stty cols 80 rows 14        # asciinema 2.x records the current terminal size
    export TERM=xterm-256color LANG=C.UTF-8
    asciinema rec demo.cast --overwrite -c "python scripts/demo_run.py"
    agg --font-size 16 demo.cast docs/assets/demo.gif
"""
import random
import time

from tqdm import tqdm

from tqdm_tag import Tag, TqdmTag

N = 60
DELAY = 0.06

rng = random.Random(4)
res = ["error" if (r := rng.random()) < 0.07 else "warn" if r < 0.22 else "ok" for _ in range(N)]

print("# plain tqdm")
for _ in tqdm(range(N), ncols=78):
    time.sleep(DELAY)

print("\n# tqdm-tag")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    legend=True,
    ncols=78,
)
for i in pbar:
    time.sleep(DELAY)
    if res[i] != "ok":
        pbar.tag(res[i])
