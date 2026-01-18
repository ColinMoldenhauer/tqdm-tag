# ex1: general
from tqdm_tag import tqdm_status

N = 100
for _ in (pbar := tqdm_status(
    range(N),
    total=N,
)):
    if _ == 1: pbar.set_tag("warn", "yellow")
    if _ == 30: pbar.set_tag("warn")
    if _ == 90: pbar.set_tag("error", "red")


# ex2: update color once done
import time
from tqdm_tag import tqdm_status

N = 9
for _ in (pbar := tqdm_status(
    range(N),
    total=N,
    colour="red",
)):
    time.sleep(.2)
    if _ == N-1: pbar.set_tag("default", "green")

# ex3: error
from tqdm_tag import tqdm_error

N = 100
for _ in (pbar := tqdm_error(
    range(N),
    total=N,
)):
    if _ == 1: pbar.warn()
    if _ == 30: pbar.error(color="red")

