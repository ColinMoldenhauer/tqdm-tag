# tqdm-tag

> Color-code individual items in a tqdm progress bar by tagging them with a status.

[![PyPI](https://img.shields.io/pypi/v/tqdm-tag)](https://pypi.org/project/tqdm-tag/)
[![Python](https://img.shields.io/pypi/pyversions/tqdm-tag)](https://pypi.org/project/tqdm-tag/)
[![Docs](https://readthedocs.org/projects/tqdm-tag/badge/?version=latest)](https://tqdm-tag.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**tqdm-tag** extends [tqdm](https://tqdm.github.io/) so you can call `pbar.tag("warn")` or `pbar.tag("error")` on any item inside your loop. The corresponding segment of the progress bar fills with that tag's color, giving you an at-a-glance overview of where issues occurred — without waiting for the loop to finish.

---

![demo](assets/demo.svg)

*Top: plain tqdm (monochrome). Bottom: tqdm-tag coloring each processed item by outcome.*

---

## Installation

```bash
pip install tqdm-tag
```

## Usage

`TqdmTag` is a drop-in replacement for `tqdm`. The only addition is the `.tag(name)` call:

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
)
for item in pbar:
    result = process(item)
    if result.has_warning:
        pbar.tag("warn")
    if result.has_error:
        pbar.tag("error")
```

### Define tags upfront

Pass `tag_to_status` and `tag_to_color` at construction time (integer statuses decide which color wins when a bar segment contains multiple items):

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
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
    if i == 30: pbar.tag("warn")           # reuse tag (no color needed)
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

### Pre-configured error class

`TqdmErrorTag` ships with `warn` (yellow) and `error` (red) already wired up:

```python
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100))
for i in pbar:
    if i % 20 == 0: pbar.warn()
    if i == 95:     pbar.error()
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
| `TqdmTag` | Core class — drop-in `tqdm` replacement with `.tag()` support |
| `TqdmErrorTag` | Subclass pre-wired with `warn` / `error` tags and `.warn()` / `.error()` helpers |
| `ColoredBar` | Internal `Bar` subclass that renders ANSI-colored segments |

Full API reference: **[tqdm-tag.readthedocs.io](https://tqdm-tag.readthedocs.io)**

## License

[MIT](LICENSE) © Colin Moldenhauer
