<p align="center">
  <img src="assets/logo-text.png" alt="tqdm-tag" height="120"/>
</p>

# tqdm-tag

**tqdm-tag** enhances [tqdm](https://tqdm.github.io/) progress bars by letting you assign a colored status tag to each item as it is processed — making warnings, errors, or any custom outcome immediately visible in the progress bar itself.

## Installation

```bash
pip install tqdm-tag
```

## Quick start

`TqdmErrorTag` is a drop-in replacement for `tqdm` — swap the class name and you're done. Call `.warn()` or `.error()` on any item to color that segment of the bar:

```python
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100), legend=True, desc="Processing")
for item in pbar:
    result = process(item)
    if result.has_warning: pbar.warn()
    if result.has_error:   pbar.error()
```

With `legend=True`, a live second line below the bar shows running counts:

$\texttt{Processing:\ \ 73\%|}\color[RGB]{166,227,161}{\texttt{████████████}}\color[RGB]{249,226,175}{\texttt{███}}\color[RGB]{166,227,161}{\texttt{███}}\color[RGB]{243,139,168}{\texttt{█}}\color[RGB]{170,170,170}{\texttt{████}}\color[RGB]{255,255,255}{\texttt{ |\ 73/100\ [00:03{<}00:01,\ 12.5it/s]}}$

$\color[RGB]{249,226,175}{\texttt{█\ warn:\ 4}}$ &ensp; $\color[RGB]{243,139,168}{\texttt{█\ error:\ 1}}$

See the [API reference](api.md) for full class and method documentation.

## Features

- **Drop-in replacement** — swap `tqdm` for `TqdmErrorTag` and add `.warn()` / `.error()` calls. No other changes required.
- **`Tag` dataclass** — groups name, color, and status in one object; status auto-assigned if omitted.
- **Live legend** — `legend=True` renders a second line below the bar with a colored swatch and count per tag, updating in real time.
- **Dynamic tags** — define tags upfront via `tags=[...]` or register them on the fly by passing a `Tag` object to `.tag()`.
- **Color support** — named colors (`"red"`, `"yellow"`, …) and hex strings (`"#ff4444"`).
- **Status reduction** — configure how multiple tagged items within one bar segment are combined (`max`, `min`, or any callable). Genuinely mixed segments render as a proportional fg/bg color blend instead of flattening to one winner.
- **Custom legend** — `legend_format` accepts a callable for full control over the legend line.
- **Resumable bars** — `initial` and `initial_status` pick a bar back up mid-run, restoring per-item tag history rather than starting the display from scratch.
- **Retag by index** — `.tag(..., index=i)` overwrites a specific item's status without advancing the bar, for retry logic in manual mode or out-of-order iterables.

## Examples

### TqdmErrorTag with legend

The fastest way to get started — pre-wired with `warn` (yellow) and `error` (red):

```python
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100), legend=True, desc="Processing")
for i in pbar:
    if i % 20 == 0: pbar.warn()
    if i == 95:     pbar.error()
```

### Custom tags with TqdmTag

Use `Tag` objects to group name, color, and status together. `status` is auto-assigned if omitted:

```python
from tqdm_tag import Tag, TqdmTag

pbar = TqdmTag(
    range(100),
    tags=[Tag("warn", color="yellow"), Tag("error", color="red")],
    legend=True,
)
for i in pbar:
    if i == 10: pbar.tag("warn")
    if i == 80: pbar.tag("error")
```

!!! note
    When `total` is known, per-item status is stored in a fixed `uint8` array (0-255) for memory efficiency, so at most 256 distinct status values are available. Registering a `Tag` (or calling `.tag()`) with a `status` outside that range raises a warning at registration time, ahead of the `OverflowError` it would otherwise cause once an item is actually tagged with it.

### Add tags dynamically

Pass a `Tag` object to `.tag()` to register and apply a new tag in one call. Subsequent calls can use the name string:

```python
from tqdm_tag import Tag, TqdmTag

pbar = TqdmTag(range(100))
for i in pbar:
    if i == 10: pbar.tag(Tag("warn",  color="yellow"))  # registers + applies
    if i == 30: pbar.tag("warn")                        # reuse by name
    if i == 80: pbar.tag(Tag("error", color="red"))
```

### Turn the whole bar green on success

```python
import time
from tqdm_tag import TqdmTag

items = range(50)
pbar = TqdmTag(items, colour="red")
for i in pbar:
    time.sleep(0.05)
    if i == len(items) - 1:
        pbar.tag("default", color="green")
```

### Customize the legend

Tags are ordered by status value. Pass `legend_format` to take full control — the callable receives `tag_counts` (dict of name → count) and `tag_to_color` (dict of name → color) and must return a string:

```python
def my_legend(counts, colors):
    return "  ".join(f"[{k.upper()}={v}]" for k, v in counts.items())

pbar = TqdmErrorTag(range(100), legend=True, legend_format=my_legend)
```

Every item starts out under the implicit `"default"` tag. Rename it with `default_tag_name` (e.g. if `"default"` collides with one of your own tag names), and show its running count in the legend with `legend_show_default`:

```python
pbar = TqdmTag(
    range(100),
    tags=[Tag("warn", color="yellow")],
    default_tag_name="pending",
    legend=True,
    legend_show_default=True,  # legend now includes "pending: N"
)
for i in pbar:
    if i == 10: pbar.tag("warn")
    if i == 90: pbar.tag("pending", color="green")  # re-color the default tag
```

### Reduce operation for dense bars

When a terminal is narrow, multiple items share one bar segment. Use `reduce_op` to choose which status wins:

```python
from tqdm_tag import Tag, TqdmTag

pbar = TqdmTag(
    range(100),
    tags=[Tag("warn", color="yellow", status=1), Tag("error", color="red", status=2)],
    reduce_op=max,
    reduce_ignore_default=True,
)
for i in pbar:
    if i % 10 == 1: pbar.tag("warn")
    if i % 10 == 2: pbar.tag("error")
```

A segment that's genuinely mixed (not every item shares one status) doesn't just flatten to `reduce_op`'s winner — it's reduced a second time over whatever's left, and rendered as a single character split proportionally between the winner's color (foreground) and the runner-up's color (background), so a minority status stays visible instead of being fully outvoted or fully hiding the majority.

!!! note
    Blending only applies with the default Unicode charset; `ascii=True` bars fall back to the flat winner color, since ASCII has no sub-character glyphs to blend with.

### Resume a bar after a restart

Pass `initial` (the number of items already done) so the bar picks up at the right percentage, and `initial_status` to restore the previous run's per-item tags instead of showing that prefix as untagged:

```python
from tqdm_tag import Tag, TqdmTag

tags = [Tag("warn", color="yellow", status=1), Tag("error", color="red", status=2)]

# first run got 30/100 done, with items 5 and 12 warned, item 21 errored
pbar = TqdmTag(
    range(30, 100),
    total=100,
    initial=30,
    tags=tags,
    initial_status={5: 1, 12: 1, 21: 2},  # {index: status}, e.g. loaded from a checkpoint
)
for i in pbar:
    ...
```

`initial_status` also accepts a sparse `(2, N)` array (`[indices, statuses]`) or a dense `(total,)` array giving every item's status directly.

### Retag an item by index

Pass `index` to `.tag()` to target a specific slot instead of the current item. `tag()` never auto-advances the bar when `index` is given, so it's safe to overwrite an already-counted item's status — the main use case is retry logic in manual (non-iterable) mode:

```python
from tqdm_tag import Tag, TqdmTag

tags = [Tag("success", color="green", status=1), Tag("error", color="red", status=2)]
pbar = TqdmTag(total=len(items), tags=tags)

for i, item in enumerate(items):
    try:
        process(item)
        pbar.tag("success")
    except Exception:
        pbar.tag("error")  # n advances either way

# later: retry failed items, flip their status without touching n
for i in failed_indices:
    if retry(items[i]):
        pbar.tag("success", index=i)
```

`index` also fits out-of-order iterables (e.g. `concurrent.futures.as_completed`), where the true slot for a completed item has to be looked up rather than assumed from completion order. Works whether or not `total` is known.
