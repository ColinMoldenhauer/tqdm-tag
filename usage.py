import time
from tqdm_tag import TqdmTag, TqdmErrorTag

N = 50
DELAY = 0.04


# ---------------------------------------------------------------------------
# Ex 1: Tags defined upfront; bar segments turn yellow/red at specific items
# ---------------------------------------------------------------------------
print("\nEx 1: Tags defined upfront (warn=yellow at item 10, error=red at item 40)")
pbar = TqdmTag(
    range(N),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.tag("warn")
    if i == 40: pbar.tag("error")


# ---------------------------------------------------------------------------
# Ex 2: Tags added dynamically during iteration (no upfront declaration)
# ---------------------------------------------------------------------------
print("\nEx 2: Tags added on the fly (warn=yellow at 10 & 30, error=red at 40)")
pbar = TqdmTag(range(N), desc="Processing")
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.tag("warn",  color="yellow")
    if i == 30: pbar.tag("warn")             # reuse tag (color already known)
    if i == 40: pbar.tag("error", color="red")


# ---------------------------------------------------------------------------
# Ex 3: Start red, flip the whole bar to green on success
# ---------------------------------------------------------------------------
print("\nEx 3: Bar starts red, turns green when last item completes")
pbar = TqdmTag(range(N), colour="red", desc="Processing")
for i in pbar:
    time.sleep(DELAY)
    if i == N - 1:
        pbar.tag("default", color="green")


# ---------------------------------------------------------------------------
# Ex 4: TqdmErrorTag convenience class (.warn() / .error() helpers)
# ---------------------------------------------------------------------------
print("\nEx 4: TqdmErrorTag with .warn() and .error() helpers")
pbar = TqdmErrorTag(range(N), desc="Processing")
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.warn()
    if i == 40: pbar.error()


# ---------------------------------------------------------------------------
# Ex 5: reduce_op — multiple items share one bar segment; max status wins
# ---------------------------------------------------------------------------
print("\nEx 5: reduce_op=max — highest severity wins when items share a segment")
pbar = TqdmTag(
    range(N),
    reduce_op=max,
    reduce_ignore_default=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 10 == 1: pbar.tag("warn",  color="yellow", status=1)
    if i % 10 == 2: pbar.tag("error", color="red",    status=2)


# ---------------------------------------------------------------------------
# Ex 6: legend=True — a live legend line below the bar shows tag counts
# ---------------------------------------------------------------------------
print("\nEx 6: legend=True — second line below bar shows colored tag counts")
pbar = TqdmTag(
    range(N),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
    legend=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 15 == 3:  pbar.tag("warn")
    if i % 25 == 12: pbar.tag("error")
