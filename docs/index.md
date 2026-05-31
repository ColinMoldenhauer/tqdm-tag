# tqdm-tag

**tqdm-tag** enhances [tqdm](https://tqdm.github.io/) progress bars by letting you assign a colored status tag to each item as it is processed — making warnings, errors, or any custom outcome immediately visible in the progress bar itself.

```{toctree}
:maxdepth: 2
:hidden:

api
```

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

The bar fills with yellow for warnings and red for errors as the loop runs. With `legend=True`, a live second line below the bar shows running counts:

```
Processing:  73%|████████████████████    | 73/100 [00:03<00:01, 12.5it/s]
■ warn: 4   ■ error: 1
```

## API reference

See {doc}`api` for full class and method documentation.

## Features

- **Drop-in replacement** — swap `tqdm` for `TqdmErrorTag` and add `.warn()` / `.error()` calls. No other changes required.
- **Live legend** — `legend=True` renders a second line below the bar with a colored swatch and count per tag, updating in real time.
- **Dynamic tags** — define tags upfront or add them on the fly during iteration.
- **Color support** — named colors (`"red"`, `"yellow"`, …) and hex codes (`"#ff4444"`).
- **Status reduction** — configure how multiple tagged items within one bar segment are combined (`max`, `min`, or any callable).
- **Custom legend** — `legend_format` accepts a callable for full control over the legend line.

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

For full control over tag names, colors, and status values:

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
    legend=True,
)
for i in pbar:
    if i == 10: pbar.tag("warn")
    if i == 80: pbar.tag("error")
```

### Add tags dynamically

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(range(100))
for i in pbar:
    if i == 10: pbar.tag("warn",  color="yellow")   # first use creates the tag
    if i == 30: pbar.tag("warn")                    # reuse (color already known)
    if i == 80: pbar.tag("error", color="red")
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

Tags added dynamically during iteration appear in the legend as soon as they are first used.

### Reduce operation for dense bars

When a terminal is narrow, multiple items share one bar segment. Use `reduce_op` to choose which status wins:

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    reduce_op=max,
    reduce_ignore_default=True,
)
for i in pbar:
    if i % 10 == 1: pbar.tag("warn",  color="yellow", status=1)
    if i % 10 == 2: pbar.tag("error", color="red",    status=2)
```
