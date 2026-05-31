import time
from tqdm_tag import Tag, TqdmTag, TqdmErrorTag

N = 50
DELAY = 0.04


# ---------------------------------------------------------------------------
# Ex 1: Tags defined upfront via Tag objects
# ---------------------------------------------------------------------------
print("\nEx 1: Tags defined upfront (warn=yellow at item 10, error=red at item 40)")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.tag("warn")
    if i == 40: pbar.tag("error")


# ---------------------------------------------------------------------------
# Ex 2: Tags added dynamically — by string or by Tag object
# ---------------------------------------------------------------------------
print("\nEx 2: Tags added on the fly (string or Tag object)")
pbar = TqdmTag(range(N), desc="Processing")
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.tag(Tag("warn",  color="yellow"))   # Tag object registers + applies
    if i == 30: pbar.tag("warn")                         # string reuses existing tag
    if i == 40: pbar.tag(Tag("error", color="red"))


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
    tags=[Tag("warn", color="yellow", status=1), Tag("error", color="red", status=2)],
    reduce_op=max,
    reduce_ignore_default=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 10 == 1: pbar.tag("warn")
    if i % 10 == 2: pbar.tag("error")


# ---------------------------------------------------------------------------
# Ex 6: legend=True — a live legend line below the bar shows tag counts
# ---------------------------------------------------------------------------
print("\nEx 6: legend=True — second line below bar shows colored tag counts")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    legend=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 15 == 3:  pbar.tag("warn")
    if i % 25 == 12: pbar.tag("error")
