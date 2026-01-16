# tqdm_color
Enhance tqdm progress bars with colored segments

## Usage
```python
from tqdm_color import tqdm_error


for i in (pbar := tqdm_error(range(100)):
    if i == 0:
        pbar.warn()

    if i == 60:
        pbar.error()
```
