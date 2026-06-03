<p align="center">
  <img src="../assets/logo-text.png" alt="tqdm-tag" height="120"/>
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

$\texttt{Processing:\ \ 73}\\%|\color{#a6e3a1}{\texttt{████████████}}\color{#f9e2af}{\texttt{███}}\color{#a6e3a1}{\texttt{███}}\color{#f38ba8}{\texttt{█}}\color{#aaaaaa}{\texttt{████}}\color{#ffffff}{\texttt{ |\ 73/100\ [00:03{<}00:01,\ 12.5it/s]}}$

$\color{#f9e2af}{\texttt{█\ warn:\ 4}}$ &ensp; $\color{#f38ba8}{\texttt{█\ error:\ 1}}$

See the [API reference](api.md) for full class and method documentation.

## Features

- **Drop-in replacement** — swap `tqdm` for `TqdmErrorTag` and add `.warn()` / `.error()` calls. No other changes required.
- **`Tag` dataclass** — groups name, color, and status in one object; status auto-assigned if omitted.
- **Live legend** — `legend=True` renders a second line below the bar with a colored swatch and count per tag, updating in real time.
- **Dynamic tags** — define tags upfront via `tags=[...]` or register them on the fly by passing a `Tag` object to `.tag()`.
- **Color support** — named colors (`"red"`, `"yellow"`, …) and hex strings (`"#ff4444"`).
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
