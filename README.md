# tqdm-tag
Enhance tqdm progress bars by assigning tags and colors to iterations.

## Usage
```python
from tqdm_tag import tqdm_status

N = 100
for _ in (pbar := tqdm_status(
    range(N),
    total=N,
)):
    if _ == 1: pbar.set_tag("warn", "yellow")   # add new tag
    if _ == 30: pbar.set_tag("warn")            # reuse tag
    if _ == 90: pbar.set_tag("error", "red")    # add another tag
```

**Example 2:** change color upon completion
```python
import time
from tqdm_tag import tqdm_status

N = 10
for _ in (pbar := tqdm_status(
    range(N),
    total=N,
    colour="red",
)):
    time.sleep(.2)
    if _ == N-1: pbar.set_tag("default", "green")
```

**Example 3:** pre-defined error class
```python
from tqdm_tag import tqdm_error

N = 100
for _ in (pbar := tqdm_error(
    range(N),
    total=N,
)):
    if _ == 1: pbar.warn()
    if _ == 30: pbar.error(color="red")
```

