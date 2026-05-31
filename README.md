# tqdm-tag

> Color-code individual items in a tqdm progress bar by tagging them with a status.

[![PyPI](https://img.shields.io/pypi/v/tqdm-tag)](https://pypi.org/project/tqdm-tag/)
[![Python](https://img.shields.io/pypi/pyversions/tqdm-tag)](https://pypi.org/project/tqdm-tag/)
[![Docs](https://readthedocs.org/projects/tqdm-tag/badge/?version=latest)](https://tqdm-tag.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**tqdm-tag** extends [tqdm](https://tqdm.github.io/) so you can call `pbar.warn()` or `pbar.error()` on any item inside your loop. The corresponding segment of the progress bar fills with that tag's color, giving you an at-a-glance overview of where issues occurred — without waiting for the loop to finish.

---

![demo](assets/demo.svg)

*Top: plain tqdm (monochrome). Bottom: tqdm-tag coloring each processed item by outcome.*

---

## Installation

```bash
pip install tqdm-tag
```

## Usage

`TqdmErrorTag` is a drop-in replacement for `tqdm` — swap the class name and you're done. Call `.warn()` or `.error()` on any item to color that segment of the bar:

```python
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100), legend=True, desc="Processing")
for item in pbar:
    result = process(item)
    if result.has_warning: pbar.warn()
    if result.has_error:   pbar.error()
```

The bar segments fill with yellow/red as the loop runs. With `legend=True`, a live second line below shows running counts:

```
Processing:  73%|████████████████████    | 73/100 [00:03<00:01, 12.5it/s]
■ warn: 4   ■ error: 1
```

### Custom tags with TqdmTag

For full control over tag names, colors, and status values use `TqdmTag` directly. Pass `tag_to_status` and `tag_to_color` at construction time:

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

### Add tags on the fly

Omit `tag_to_status`/`tag_to_color` and pass a color directly to `.tag()` — new tags are registered automatically:

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(range(100))
for i in pbar:
    if i == 10: pbar.tag("warn",  color="yellow")
    if i == 30: pbar.tag("warn")           # reuse tag (color already known)
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

Tags in the legend are ordered by status value. Pass a `legend_format` callable to take full control — it receives `tag_counts` (dict of name → count) and `tag_to_color` (dict of name → color):

```python
def my_legend(counts, colors):
    return "  ".join(f"[{k.upper()}={v}]" for k, v in counts.items())

pbar = TqdmErrorTag(range(100), legend=True, legend_format=my_legend)
```

### Reduce operation for dense bars

When the terminal is narrow, multiple items share one bar segment. Use `reduce_op` to control which status wins, and `reduce_ignore_default` to skip untagged items when reducing:

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    reduce_op=max,              # highest-severity status wins
    reduce_ignore_default=True, # don't let untagged items dilute the color
)
for i in pbar:
    if i % 10 == 1: pbar.tag("warn",  color="yellow", status=1)
    if i % 10 == 2: pbar.tag("error", color="red",    status=2)
```

## API

| Class | Description |
|---|---|
| `TqdmErrorTag` | Drop-in replacement with pre-wired `warn` / `error` tags and `.warn()` / `.error()` helpers |
| `TqdmTag` | Core class for fully custom tag names, colors, and status values |
| `ColoredBar` | Internal `Bar` subclass that renders ANSI-colored segments |

Full API reference: **[tqdm-tag.readthedocs.io](https://tqdm-tag.readthedocs.io)**

## License

[MIT](LICENSE) © Colin Moldenhauer
