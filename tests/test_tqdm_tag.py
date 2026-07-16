import io
import numpy as np
import pytest
from tqdm import TqdmWarning
from tqdm_tag import Tag, TqdmTag, TqdmErrorTag, ColoredBar


# ---------------------------------------------------------------------------
# Tag dataclass
# ---------------------------------------------------------------------------

def test_tag_defaults():
    t = Tag("ok")
    assert t.name == "ok"
    assert t.color is None
    assert t.status is None


def test_tag_fields():
    t = Tag("err", color="red", status=2)
    assert t.color == "red"
    assert t.status == 2


# ---------------------------------------------------------------------------
# TqdmTag iteration and status tracking
# ---------------------------------------------------------------------------

def test_basic_iteration():
    out = io.StringIO()
    results = []
    with TqdmTag(range(5), file=out, disable=False) as pbar:
        for item in pbar:
            results.append(item)
    assert results == list(range(5))


def test_tag_records_status():
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    with TqdmTag(range(4), tags=[warn], file=out) as pbar:
        for i, _ in enumerate(pbar):
            if i == 2:
                pbar.tag("warn")
    # item 2 should carry status 1, others default (0)
    assert pbar._item_status[2] == 1
    assert pbar._item_status[0] == 0
    assert pbar._item_status[3] == 0


def test_tag_with_tag_object():
    out = io.StringIO()
    err = Tag("error", color="red", status=2)
    with TqdmTag(range(3), tags=[err], file=out) as pbar:
        for i, _ in enumerate(pbar):
            if i == 1:
                pbar.tag(err)
    assert pbar._item_status[1] == 2


def test_unknown_total_uses_list():
    out = io.StringIO()
    def gen():
        yield from range(3)
    with TqdmTag(gen(), file=out) as pbar:
        for _ in pbar:
            pass
    assert isinstance(pbar._item_status, list)
    assert len(pbar._item_status) == 3


def test_tag_then_break_still_counts_current_item():
    """Tagging the current item and immediately `break`-ing out of the loop
    must still advance `n` to include that item.

    `tqdm.__iter__` (the base class's generator) only advances `n` in code
    positioned *after* its `yield` - a `break` throws `GeneratorExit` at
    that suspended `yield`, skipping the increment entirely, so the
    just-tagged item's status was recorded but silently excluded from
    `n`/`total` (and thus from the range `ColoredBar.__format__` actually
    paints), even though the legend counter (updated independently in
    `tag()`) correctly reflects it.
    """
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    pbar = TqdmTag(range(12), tags=[warn], file=out, mininterval=0, disable=False)
    for i in pbar:
        if i == 9:
            pbar.tag("warn")
            break

    assert pbar.n == 10
    assert pbar._item_status[9] == 1


# ---------------------------------------------------------------------------
# TqdmErrorTag convenience API
# ---------------------------------------------------------------------------

def test_error_tag_warn_error():
    out = io.StringIO()
    with TqdmErrorTag(range(5), file=out) as pbar:
        for i, _ in enumerate(pbar):
            if i == 1:
                pbar.warn()
            if i == 3:
                pbar.error()
    assert pbar._item_status[1] == TqdmErrorTag.WARN.status
    assert pbar._item_status[3] == TqdmErrorTag.ERROR.status
    assert pbar._item_status[0] == 0


def test_error_tag_predefined_tags():
    assert TqdmErrorTag.WARN.color == "yellow"
    assert TqdmErrorTag.ERROR.color == "red"
    assert TqdmErrorTag.ERROR.status > TqdmErrorTag.WARN.status


# ---------------------------------------------------------------------------
# _get_colors static method
# ---------------------------------------------------------------------------

def test_get_colors_all_default():
    status_to_tag = {0: "default", 1: "warn"}
    tag_to_color = {"default": None, "warn": "yellow"}
    colors = TqdmTag._get_colors(
        n_segments=4,
        item_status=np.zeros(4, dtype=np.uint8),
        status_to_tag=status_to_tag,
        tag_to_color=tag_to_color,
        default_status=0,
    )
    assert colors == [None, None, None, None]


def test_get_colors_mixed():
    item_status = np.array([0, 0, 1, 1], dtype=np.uint8)
    status_to_tag = {0: "default", 1: "warn"}
    tag_to_color = {"default": None, "warn": "yellow"}
    colors = TqdmTag._get_colors(
        n_segments=4,
        item_status=item_status,
        status_to_tag=status_to_tag,
        tag_to_color=tag_to_color,
        default_status=0,
    )
    assert colors[:2] == [None, None]
    assert colors[2:] == ["yellow", "yellow"]


def test_get_colors_empty():
    colors = TqdmTag._get_colors(
        n_segments=5,
        item_status=np.array([], dtype=np.uint8),
        status_to_tag={0: "default"},
        tag_to_color={"default": None},
        default_status=0,
    )
    assert colors == [None] * 5


def test_get_colors_segment_boundary_matches_filled():
    """`_get_colors`'s bucket boundaries must agree with the `filled`
    boundary `ColoredBar.__format__` derives from the same `frac`, or the
    colored segment renders displaced from the true progress edge.

    Concrete regression case: total=50, n_segments=20, n=33 (item at
    0-indexed position 32 just tagged). `np.array_split` puts that item in
    bucket 11, while `ColoredBar.__format__` independently computes
    `filled=13` from `frac=n/total` - a 2-segment disagreement.
    """
    total, n_segments, n = 50, 20, 33
    item_status = np.zeros(total, dtype=np.uint8)
    item_status[n - 1] = 1  # tag the just-processed item

    colors = TqdmTag._get_colors(
        n_segments=n_segments,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    tagged_segment = colors.index("yellow")

    # same boundary ColoredBar.__format__ uses to pick which segments render
    # as fully "filled" for this frac
    frac = n / total
    nsyms = len(ColoredBar.UTF) - 1
    filled, _ = divmod(int(frac * n_segments * nsyms), nsyms)

    assert tagged_segment == filled


@pytest.mark.parametrize("total", range(10, 60, 7))
@pytest.mark.parametrize("n_segments", range(2, 21, 3))
def test_get_colors_boundary_never_off_by_more_than_one(total, n_segments):
    """Across a range of (total, n_segments), the segment `_get_colors`
    assigns a tagged item to must never diverge from `filled` by more than
    one segment - a wider divergence would leave a tagged status invisible
    or visibly out of place relative to the fill edge.

    Only exercises `n_segments <= total` (the branch the reported bug hit):
    when `n_segments > total`, several segments legitimately map to the same
    item (many-to-one), so `colors.index("yellow")` no longer corresponds
    to a single boundary and isn't comparable to `filled` this way - see
    `test_get_colors_sparse_branch_*` below for that branch instead.
    """
    if n_segments > total:
        pytest.skip("many-to-one mapping in this branch; see sparse-branch tests")

    nsyms = len(ColoredBar.UTF) - 1
    for n in range(1, total + 1):
        item_status = np.zeros(total, dtype=np.uint8)
        item_status[n - 1] = 1

        colors = TqdmTag._get_colors(
            n_segments=n_segments,
            item_status=item_status,
            status_to_tag={0: "default", 1: "warn"},
            tag_to_color={"default": None, "warn": "yellow"},
            default_status=0,
        )
        tagged_segment = colors.index("yellow")

        frac = n / total
        filled, _ = divmod(int(frac * n_segments * nsyms), nsyms)

        assert abs(tagged_segment - filled) <= 1, (
            f"total={total} n_segments={n_segments} n={n}: "
            f"tagged_segment={tagged_segment} filled={filled}"
        )


def test_get_colors_sparse_branch_uses_same_boundary_formula():
    """When there are more segments than items (`n_segments > total`), each
    segment should sample the item at its bucket's start edge - the same
    `edges = floor(k * total / n_segments)` formula the dense branch and
    `ColoredBar.__format__`'s `filled` both use - rather than an
    independently-tuned `np.linspace` mapping that isn't guaranteed to agree.
    """
    total, n_segments = 7, 20
    item_status = (np.arange(total, dtype=np.uint8) % 2)  # alternating 0/1
    colors = TqdmTag._get_colors(
        n_segments=n_segments,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    edges = (np.arange(n_segments) * total) // n_segments
    expected = ["yellow" if item_status[e] else None for e in edges]
    assert colors == expected


def test_get_colors_sparse_branch_last_item_reaches_last_segment():
    """Tagging the final item (100% complete) must colour the final bar
    segment - the sparse-branch analogue of the dense-branch boundary
    check, verifying the last item is never displaced off the bar's edge.
    """
    total, n_segments = 10, 20
    item_status = np.zeros(total, dtype=np.uint8)
    item_status[-1] = 1
    colors = TqdmTag._get_colors(
        n_segments=n_segments,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    assert colors[-1] == "yellow"


# ---------------------------------------------------------------------------
# ColoredBar rendering
# ---------------------------------------------------------------------------

def test_colored_bar_empty():
    bar = ColoredBar(0.0, default_len=10, segment_colours=[None] * 10)
    rendered = f"{bar}"
    assert len(rendered) == 10


def test_colored_bar_full():
    bar = ColoredBar(1.0, default_len=10, segment_colours=[None] * 10)
    rendered = f"{bar}"
    assert len(rendered) == 10


def test_colored_bar_clamps_frac():
    with pytest.warns(TqdmWarning):
        bar = ColoredBar(1.5, default_len=5, segment_colours=[None] * 5)
    assert bar.frac == 1.0


def test_colored_bar_ascii_charset():
    bar = ColoredBar(0.5, default_len=10, charset=ColoredBar.ASCII,
                     segment_colours=[None] * 10)
    rendered = f"{bar}"
    assert len(rendered) == 10


def test_colored_bar_hex_color():
    bar = ColoredBar(1.0, default_len=2, segment_colours=["#ff0000", "#ff0000"])
    rendered = f"{bar}"
    assert "\x1b[38;2;255;0;0m" in rendered


def test_colored_bar_named_color():
    bar = ColoredBar(1.0, default_len=2, segment_colours=["red", "red"])
    rendered = f"{bar}"
    assert "\x1b[31m" in rendered
