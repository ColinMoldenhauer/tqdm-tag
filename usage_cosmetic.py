import time
from tqdm_tag import Tag, TqdmTag, TqdmErrorTag

N = 50
DELAY = 0.04


# ---------------------------------------------------------------------------
# Ex 1: legend_format as a str template — wrap the default swatch rendering
# ---------------------------------------------------------------------------
print("\nEx 1: legend_format str template — prefix the default swatch legend")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    legend=True,
    legend_format="tags: {legend}",
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 15 == 3:  pbar.tag("warn")
    if i % 25 == 12: pbar.tag("error")


# ---------------------------------------------------------------------------
# Ex 2: legend_format as a callable — full control over the legend line
# ---------------------------------------------------------------------------
print("\nEx 2: legend_format callable — bracketed, upper-cased tag counts")


def my_legend(counts, colors):
    return "  ".join(f"[{name.upper()}={count}]" for name, count in counts.items())


pbar = TqdmErrorTag(
    range(N),
    legend=True,
    legend_format=my_legend,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i == 10: pbar.warn()
    if i == 40: pbar.error()


# ---------------------------------------------------------------------------
# Ex 3: default_tag_name — rename the implicit "default" tag
# ---------------------------------------------------------------------------
print("\nEx 3: default_tag_name — call the untagged state 'pending' instead")
pbar = TqdmTag(
    range(N),
    tags=[Tag("done", color="green")],
    default_tag_name="pending",
    legend=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 5 == 0: pbar.tag("done")


# ---------------------------------------------------------------------------
# Ex 4: legend_show_default — surface the untagged count in the legend too
# ---------------------------------------------------------------------------
print("\nEx 4: legend_show_default — legend also counts still-untagged items")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    legend=True,
    legend_show_default=True,
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 15 == 3:  pbar.tag("warn")
    if i % 25 == 12: pbar.tag("error")


# ---------------------------------------------------------------------------
# Ex 5: all together — renamed default tag, shown in a custom legend
# ---------------------------------------------------------------------------
print("\nEx 5: default_tag_name + legend_show_default + legend_format combined")
pbar = TqdmTag(
    range(N),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    default_tag_name="untouched",
    legend=True,
    legend_show_default=True,
    legend_format="status: {legend}",
    desc="Processing",
)
for i in pbar:
    time.sleep(DELAY)
    if i % 15 == 3:  pbar.tag("warn")
    if i % 25 == 12: pbar.tag("error")
