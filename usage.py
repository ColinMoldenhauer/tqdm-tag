# ex1: general
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),   # your iterable
    tag_to_status={"warn": 1, "error": 2},
    tag_to_color={"warn": "yellow", "error": "red"},
)
for i in pbar:
    if i == 1: pbar.tag("warn")
    if i == 90: pbar.tag("error")


# ex2: general
from tqdm_tag import TqdmTag

pbar = TqdmTag(range(100))     # initialize without pre-defined tags
for i in pbar:
    if i == 1: pbar.tag("warn", "yellow")   # add new tag (and color)
    if i == 30: pbar.tag("warn")            # reuse tag
    if i == 90: pbar.tag("error", "red", status=3)    # another tag (with custom status)


# ex3: update color once done
import time
from tqdm_tag import TqdmTag

it = range(100)
pbar = TqdmTag(
    it,
    colour="red",
)
for i in pbar:
    time.sleep(.01)
    if i == len(it)-1: pbar.tag("default", "green")

# ex4: error
from tqdm_tag import TqdmErrorTag

pbar = TqdmErrorTag(range(100))
for i in pbar:
    if i == 1: pbar.warn()
    if i == 30: pbar.error(color="red")


# adv1: reduce operation
from tqdm_tag import TqdmTag

pbar = TqdmTag(
    range(100),
    reduce_op=max,  # use highest status value
)
for i in pbar:
    if i == 1: pbar.tag("tag1", status=1, color="green")
    if i == 2: pbar.tag("tag2", status=2, color="red")

pbar = TqdmTag(
    range(100),
    reduce_op=min,  # use lowest status value
    reduce_ignore_default=True,
)
for i in pbar:
    if i == 1: pbar.tag("tag1", status=1, color="green")
    if i == 2: pbar.tag("tag2", status=2, color="red")

