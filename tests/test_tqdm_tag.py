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
