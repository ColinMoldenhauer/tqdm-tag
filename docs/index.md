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

`TqdmTag` is a drop-in replacement for `tqdm`. Call `pbar.tag(name)` on any item inside the loop to color that position in the bar:

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

The bar segments fill with the tag's color as the loop runs, so you see *where* and *how often* issues occurred without waiting for the loop to finish.

## API reference

See {doc}`api` for full class and method documentation.

## Features

- **Drop-in replacement** — same interface as `tqdm`, no changes required to your loop body beyond calling `.tag()`.
- **Dynamic tags** — define tags upfront or add them on the fly during iteration.
- **Color support** — named colors (`"red"`, `"yellow"`, …) and hex codes (`"#ff4444"`).
- **Status reduction** — configure how multiple tagged items within one bar segment are combined (`max`, `min`, or any callable).
- **Pre-built error class** — `TqdmErrorTag` ships with `warn` and `error` tags out of the box.

## Examples

### Define tags upfront

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
)
for i in pbar:
    if i == 10:
        pbar.tag("warn")
    if i == 80:
        pbar.tag("error")
```

### Add tags dynamically

```python
from tqdm_tag import TqdmTag

pbar = TqdmTag(range(100))
for i in pbar:
    if i == 10:
        pbar.tag("warn", color="yellow")   # first occurrence creates the tag
    if i == 80:
        pbar.tag("error", color="red")
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

`TqdmErrorTag` adds `.warn()` and `.error()` convenience methods:

```python
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100))
for i in pbar:
    if i % 20 == 0:
        pbar.warn()
    if i == 95:
        pbar.error()
```

### Reduce operation for dense bars

When a terminal is narrow, multiple items share one bar segment. Use `reduce_op` to choose which status wins:

```python
from tqdm_tag import TqdmTag

# show highest-severity status per segment
pbar = TqdmTag(
    range(100),
    reduce_op=max,
    reduce_ignore_default=True,
)
for i in pbar:
    if i % 10 == 1:
        pbar.tag("warn", color="yellow", status=1)
    if i % 10 == 2:
        pbar.tag("error", color="red", status=2)
```
