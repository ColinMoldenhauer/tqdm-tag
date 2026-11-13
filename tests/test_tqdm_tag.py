import io
import re
import warnings

import numpy as np
import pytest
from tqdm import TqdmWarning
from tqdm_tag import Tag, TqdmTag, TqdmErrorTag, ColoredBar


class FakeTTY(io.StringIO):
    """A `StringIO` that reports `isatty() == True`, so the legend's
    TTY-only rendering path (see `TqdmTag.display`) actually runs -
    plain `io.StringIO` makes `isatty()` return `False`, silently
    skipping that path in every other test in this file."""

    def isatty(self):
        return True


def render_screen(raw):
    """Replay a raw ANSI/carriage-return stream into the final visible
    terminal lines it would leave behind - `\\r`, `\\n` (with the CRLF
    translation real cooked-mode TTYs apply, which is what `TqdmTag` and
    `tqdm` itself assume) and cursor-up (`ESC[A`) are interpreted; other
    escape codes (colour, etc.) are stripped. Needed because a raw
    substring check (e.g. `"ok:" in out.getvalue()`) sees every
    intermediate frame ever written, not just what's left on screen."""
    lines = [""]
    row = col = 0

    def put(ch):
        nonlocal col
        line = lines[row]
        if len(line) < col:
            line = line + " " * (col - len(line))
        line = line[:col] + ch + line[col + 1:]
        lines[row] = line
        col += 1

    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\x1b":
            m = re.match(r"\x1b\[(\d*)([A-Za-z])", raw[i:])
            if m:
                if m.group(2) == "A":
                    row = max(0, row - (int(m.group(1)) if m.group(1) else 1))
                i += m.end()
                continue
            i += 1
        elif c == "\r":
            col = 0
            i += 1
        elif c == "\n":
            row += 1
            col = 0
            while len(lines) <= row:
                lines.append("")
            i += 1
        else:
            put(c)
            i += 1
    return lines


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


def test_partially_completed_bar_renders_untouched_items_as_default():
    """Items beyond the current progress edge sit at `_UNSET_STATUS`
    (never explicitly tagged) in the preallocated array; rendering the bar
    must resolve those to the default color rather than crashing or
    treating the sentinel as a real, out-ranking status."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    pbar = TqdmTag(range(10), tags=[warn], file=out, mininterval=0, disable=False)
    for i in pbar:
        if i == 2:
            pbar.tag("warn")
        if i == 3:
            break

    # items 4-9 were never reached, still _UNSET_STATUS internally
    assert (pbar._item_status[4:] == TqdmTag._UNSET_STATUS).all()

    colors = TqdmTag._get_colors(n_segments=10, **pbar.format_dict)
    assert colors[2] == "yellow"
    assert all(c is None for c in colors[3:])


def test_tag_with_tag_object():
    out = io.StringIO()
    err = Tag("error", color="red", status=2)
    with TqdmTag(range(3), tags=[err], file=out) as pbar:
        for i, _ in enumerate(pbar):
            if i == 1:
                pbar.tag(err)
    assert pbar._item_status[1] == 2


def test_tag_status_out_of_uint8_range_warns():
    out = io.StringIO()
    big = Tag("big", status=300)
    with pytest.warns(TqdmWarning, match="uint8"):
        TqdmTag(range(3), tags=[big], file=out)


def test_tag_call_status_out_of_uint8_range_warns():
    # tag() both registers the new status (triggering the warning) and
    # immediately writes it into the item array, which still overflows.
    out = io.StringIO()
    with TqdmTag(range(3), file=out) as pbar:
        with pytest.raises(OverflowError):
            with pytest.warns(TqdmWarning, match="uint8"):
                pbar.tag("huge", status=1000)


def test_tag_status_in_range_does_not_warn():
    out = io.StringIO()
    ok = Tag("ok", status=5)
    with warnings.catch_warnings():
        warnings.simplefilter("error", TqdmWarning)
        TqdmTag(range(3), tags=[ok], file=out)


def test_tag_status_out_of_range_no_total_does_not_warn():
    """No preallocated uint8 array exists when `total` is unknown, so the
    range restriction doesn't apply."""
    out = io.StringIO()
    def gen():
        yield from range(3)
    big = Tag("big", status=300)
    with warnings.catch_warnings():
        warnings.simplefilter("error", TqdmWarning)
        with TqdmTag(gen(), tags=[big], file=out) as pbar:
            for _ in pbar:
                pass


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
# tag(index=...) overrides
# ---------------------------------------------------------------------------

def test_tag_index_overwrites_manual_mode_without_advancing():
    """Retry-style usage: an item first tagged "error" is later flipped to
    "success" via `index=`, without double-counting it in `n`."""
    out = io.StringIO()
    tags = [Tag("success", color="green", status=1), Tag("error", color="red", status=2)]
    with TqdmTag(total=3, tags=tags, file=out) as pbar:
        pbar.tag("success")  # item 0
        pbar.tag("error")    # item 1
        assert pbar.n == 2
        assert pbar._item_status[1] == 2

        # retry item 1 succeeds - overwrite its status, `n` must not move
        pbar.tag("success", index=1)
        assert pbar.n == 2
        assert pbar._item_status[1] == 1

        pbar.tag("success")  # item 2
    assert pbar.n == 3


def test_tag_index_zero_is_respected():
    """`index=0` must not be treated as falsy (regression for `index or ...`
    style bugs)."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    with TqdmTag(total=3, tags=[warn], file=out) as pbar:
        pbar.tag("warn")             # item 0 -> warn, n=1
        pbar.tag("default", index=0)  # overwrite item 0 back to default
    assert pbar._item_status[0] == 0
    assert pbar.n == 1


def test_iter_guard_preserves_out_of_order_tag():
    """Simulates an out-of-order iterable (e.g. `as_completed`): the loop's
    own completion-order counter `i` eventually collides with a slot that
    was already explicitly tagged via `index=`; the auto default-status
    reset in `__iter__` must skip that slot rather than clobber it."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    # completion order -> true index: 0->2, 1->0, 2->1
    completion_order = [2, 0, 1]
    with TqdmTag(range(3), tags=[warn], file=out, mininterval=0) as pbar:
        for item, true_idx in zip(pbar, completion_order):
            if true_idx == 2:
                pbar.tag("warn", index=true_idx)
    # true index 2 was tagged "warn" while completion-order i was 0; later,
    # when the loop's own counter reaches i=2, its default-reset must not
    # wipe out the explicitly-tagged status at slot 2
    assert pbar._item_status[2] == 1


def test_tag_index_manual_mode_without_total():
    """`index=` overwrite/jump-ahead must also work when `total` is unknown
    and `_item_status` is a plain growable list rather than a preallocated
    array."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    with TqdmTag(total=None, tags=[warn], file=out) as pbar:
        pbar.tag("warn")     # item 0, n=1
        pbar.tag("default")  # item 1, n=2
        assert pbar.n == 2

        # retry item 0 - overwrite without advancing n
        pbar.tag("default", index=0)
        assert pbar.n == 2
        assert pbar._item_status[0] == 0

        # jump ahead to a slot beyond the list's current length - must pad
        # the gap with _UNSET_STATUS (genuinely untouched, not
        # default_status) rather than raise. Slot 5 was never seen before,
        # so this first-time index= tag also counts it (n advances).
        pbar.tag("warn", index=5)
        assert pbar.n == 3
        unset = TqdmTag._UNSET_STATUS
        assert pbar._item_status == [0, 0, unset, unset, unset, 1]


def test_tag_index_first_touch_advances_n_manual_mode():
    """A first-time `tag(..., index=i)` for a never-before-seen slot must
    count it (advance `n`), just like `index=None` would - only a *retry*
    of an already-tagged slot should leave `n` alone."""
    out = io.StringIO()
    tags = [Tag("success", color="green", status=1), Tag("error", color="red", status=2)]
    with TqdmTag(total=5, tags=tags, file=out) as pbar:
        # out-of-order manual-mode completions, e.g. as_completed(futures)
        pbar.tag("success", index=2)
        assert pbar.n == 1
        assert pbar._item_status[2] == 1

        pbar.tag("error", index=0)
        assert pbar.n == 2
        assert pbar._item_status[0] == 2

        # retry slot 0 - already seen, must not advance n again
        pbar.tag("success", index=0)
        assert pbar.n == 2
        assert pbar._item_status[0] == 1


def test_default_status_colliding_with_unset_sentinel_raises():
    """`default_status` must not collide with the reserved `_UNSET_STATUS`
    sentinel used to distinguish "never tagged" from "explicitly default"."""
    with pytest.raises(ValueError, match="_UNSET_STATUS|unset"):
        TqdmTag(total=3, default_status=TqdmTag._UNSET_STATUS)


def test_tag_index_retag_updates_legend_counts():
    """Retagging a slot via `index=` must move its legend count from the
    old tag to the new one, not leave a stale increment behind
    (regression for the legend-count-drift bug)."""
    out = io.StringIO()
    pool = Tag("pool", color="magenta", status=1)
    with TqdmTag(
        total=3,
        tags=[pool],
        default_tag_name="success",
        legend=True,
        legend_show_default=True,
        file=out,
    ) as pbar:
        pbar.tag("pool", index=0)      # first touch of slot 0 -> counts it
        pbar.tag("success", index=0)  # retry of slot 0 -> already counted
        pbar.tag("success", index=1)  # first touch of slot 1 -> counts it
        pbar.tag("success", index=2)  # first touch of slot 2 -> counts it

    assert pbar.n == 3
    assert pbar._tag_counts == {"pool": 0}
    assert pbar._legend_tag_counts() == {"success": 3, "pool": 0}


def test_tag_index_retag_to_default_decrements_old_tag():
    """Retagging a slot back to the implicit default tag must still
    decrement whatever non-default tag previously held it."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    with TqdmTag(total=2, tags=[warn], legend=True, file=out) as pbar:
        pbar.tag("warn", index=0)
        assert pbar._tag_counts == {"warn": 1}

        pbar.tag("default", index=0)
        assert pbar._tag_counts == {"warn": 0}


def test_prune_legend_omits_zero_count_tags():
    """`prune_legend=True` must drop tags with a count of 0 from the legend,
    while leaving `_tag_counts` itself untouched."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    error = Tag("error", color="red", status=2)
    with TqdmTag(
        total=2,
        tags=[warn, error],
        legend=True,
        prune_legend=True,
        file=out,
    ) as pbar:
        assert pbar._legend_tag_counts() == {}
        pbar.tag("warn", index=0)
        assert pbar._legend_tag_counts() == {"warn": 1}
        assert pbar._tag_counts == {"warn": 1, "error": 0}


def test_prune_legend_with_show_default_hides_zero_default():
    """`prune_legend` combined with `legend_show_default` must hide the
    derived default-tag count too, once it drops to 0."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)
    with TqdmTag(
        total=2,
        tags=[warn],
        legend=True,
        legend_show_default=True,
        prune_legend=True,
        file=out,
    ) as pbar:
        pbar.tag("warn", index=0)  # first touch of slot 0 -> counts it
        pbar.tag("warn", index=1)  # first touch of slot 1 -> counts it
        assert pbar.n == 2
        assert pbar._legend_tag_counts() == {"warn": 2}


def test_legend_not_left_behind_when_leave_false():
    """`leave=False` must erase the bar *and* its legend line - `tqdm`'s own
    `close()` blanks the bar line via `display(msg="")`, but previously
    `TqdmTag.display` redrew the legend unconditionally even on that
    clearing call, leaving stray legend text on screen after close()."""
    out = FakeTTY()
    with TqdmTag(range(3), file=out, legend=True, leave=False, mininterval=0) as pbar:
        for _ in pbar:
            pbar.tag("ok", color="green")
    screen = render_screen(out.getvalue())
    assert not any("ok:" in line for line in screen)


def test_clear_also_clears_legend_line():
    """`clear()` (called directly, or by `tqdm.write()` on every live bar
    before it prints) must blank the legend line along with the bar -
    `TqdmTag` didn't override `clear()` at all previously, so the legend
    line (drawn outside tqdm's own line-tracking, in `display()`) survived
    a `clear()` call untouched, left dangling below a blanked bar line."""
    out = FakeTTY()
    pbar = TqdmTag(range(3), file=out, legend=True, mininterval=0)
    pbar.tag("ok", color="green", index=0)
    pbar.refresh()
    assert any("ok: 1" in line for line in render_screen(out.getvalue()))

    pbar.clear()
    screen = render_screen(out.getvalue())
    assert not any("ok:" in line for line in screen)
    assert not any(line.strip() for line in screen)
    pbar.close()


def test_legend_survives_tqdm_write_clear():
    """`tqdm.write()` clears every live bar via `clear()` before printing
    and redraws afterward; without the `clear()` override above, this used
    to leave a stale legend line whose position drifted with every call."""
    out = FakeTTY()
    with TqdmTag(range(3), file=out, legend=True, mininterval=0) as pbar:
        for i in pbar:
            pbar.tag("ok", color="green")
            if i == 0:
                TqdmTag.write("hello from write()", file=out)
    screen = render_screen(out.getvalue())
    assert any("hello from write()" in line for line in screen)
    assert any("100%" in line and "3/3" in line for line in screen)
    assert sum("ok: 3" in line for line in screen) == 1


def test_iter_guard_preserves_out_of_order_tag_without_total():
    """Same collision as `test_iter_guard_preserves_out_of_order_tag`, but
    with `total` unknown (`_item_status` is a list, not a numpy array)."""
    out = io.StringIO()
    warn = Tag("warn", color="yellow", status=1)

    def gen():
        yield from range(4)

    completion_order = [2, 0, 1, 3]
    with TqdmTag(gen(), tags=[warn], file=out, mininterval=0) as pbar:
        for item, true_idx in zip(pbar, completion_order):
            if true_idx == 2:
                pbar.tag("warn", index=true_idx)
    assert pbar._item_status[2] == 1
    assert isinstance(pbar._item_status, list)


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

def _colour_key(entry):
    """Dominant (winner) color for a segment, whether solid or blended."""
    return entry[0] if isinstance(entry, tuple) else entry


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


def test_get_colors_unset_sentinel_renders_as_default():
    """Segments made up entirely of `_UNSET_STATUS` (never explicitly
    tagged, e.g. not-yet-reached items) must render as the default color,
    not as a colored/flagged segment."""
    unset = TqdmTag._UNSET_STATUS
    item_status = np.full(4, unset, dtype=np.uint8)
    status_to_tag = {0: "default", 1: "warn"}
    tag_to_color = {"default": None, "warn": "yellow"}
    colors = TqdmTag._get_colors(
        n_segments=4,
        item_status=item_status,
        status_to_tag=status_to_tag,
        tag_to_color=tag_to_color,
        default_status=0,
    )
    assert colors == [None, None, None, None]


def test_get_colors_unset_sentinel_does_not_outrank_real_tag():
    """A segment mixing `_UNSET_STATUS` (untouched) items with a real tag
    must resolve to that tag's color, not the sentinel - `reduce_op=max`
    would otherwise always pick the sentinel, since it's the dtype's max
    value, silently hiding every real tag it shares a segment with."""
    unset = TqdmTag._UNSET_STATUS
    item_status = np.array([unset, unset, 1, unset], dtype=np.uint8)
    status_to_tag = {0: "default", 1: "warn"}
    tag_to_color = {"default": None, "warn": "yellow"}
    colors = TqdmTag._get_colors(
        n_segments=1,
        item_status=item_status,
        status_to_tag=status_to_tag,
        tag_to_color=tag_to_color,
        default_status=0,
    )
    assert colors == ["yellow"]


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
    tagged_segment = next(i for i, c in enumerate(colors) if _colour_key(c) == "yellow")

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
        tagged_segment = next(i for i, c in enumerate(colors) if _colour_key(c) == "yellow")

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
# _get_colors: blended (mixed-status) segments
# ---------------------------------------------------------------------------

def test_get_colors_pure_segment_stays_solid():
    """A segment whose items all share one status must still resolve to a
    plain color, not a blend tuple - blending only kicks in for genuinely
    mixed segments."""
    item_status = np.array([1, 1, 1, 1], dtype=np.uint8)
    colors = TqdmTag._get_colors(
        n_segments=1,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    assert colors == ["yellow"]


def test_get_colors_mixed_segment_blends():
    """A segment mixing one minority status into a majority status must
    reduce twice - once for the winner, once more over what's left - and
    report the minority's color plus its fraction of the segment."""
    # reduce_op=max (default): "warn" (1) outranks "default" (0)
    item_status = np.array([0, 0, 0, 1], dtype=np.uint8)
    colors = TqdmTag._get_colors(
        n_segments=1,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    assert len(colors) == 1
    winner_colour, runner_up_colour, winner_fraction = colors[0]
    assert winner_colour == "yellow"
    assert runner_up_colour is None  # "default" has no color
    assert winner_fraction == pytest.approx(0.25)


def test_get_colors_three_way_segment_uses_hierarchical_runnerup():
    """With three distinct statuses in one segment, the runner-up must be
    the highest of what's left *after* removing the winner - not simply
    the second most frequent status."""
    # error(2) > warn(1) > default(0); one error, rest split between
    # default and warn, so after peeling off "error" the runner-up must
    # be "warn" even though "default" is more frequent.
    item_status = np.array([0, 0, 0, 1, 2], dtype=np.uint8)
    colors = TqdmTag._get_colors(
        n_segments=1,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn", 2: "error"},
        tag_to_color={"default": None, "warn": "yellow", "error": "red"},
        default_status=0,
    )
    winner_colour, runner_up_colour, winner_fraction = colors[0]
    assert winner_colour == "red"
    assert runner_up_colour == "yellow"
    assert winner_fraction == pytest.approx(0.2)


def test_get_colors_blend_respects_reduce_ignore_default():
    """`reduce_ignore_default` must filter default-status items before the
    hierarchical reduce runs, same as it does for the single-status case."""
    item_status = np.array([0, 0, 1, 2], dtype=np.uint8)
    colors = TqdmTag._get_colors(
        n_segments=1,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn", 2: "error"},
        tag_to_color={"default": None, "warn": "yellow", "error": "red"},
        default_status=0,
        reduce_ignore_default=True,
    )
    winner_colour, runner_up_colour, winner_fraction = colors[0]
    assert winner_colour == "red"
    assert runner_up_colour == "yellow"
    assert winner_fraction == pytest.approx(0.5)  # 1 error / (1 error + 1 warn)


def test_get_colors_sparse_branch_never_blends():
    """When there are more segments than items, each segment maps to
    exactly one item - there's nothing to blend, so entries must stay
    plain colors even though the underlying data has mixed statuses."""
    total, n_segments = 4, 10
    item_status = np.array([0, 1, 0, 1], dtype=np.uint8)
    colors = TqdmTag._get_colors(
        n_segments=n_segments,
        item_status=item_status,
        status_to_tag={0: "default", 1: "warn"},
        tag_to_color={"default": None, "warn": "yellow"},
        default_status=0,
    )
    assert all(not isinstance(c, tuple) for c in colors)


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


def test_colored_bar_blended_segment_uses_fg_and_bg():
    """A blended (winner, runner_up, fraction) segment must render with a
    foreground escape for the winner and a background escape for the
    runner-up, wrapping a single glyph."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[("red", "green", 0.5)])
    rendered = f"{bar}"
    assert "\x1b[31m" in rendered  # red foreground
    assert "\x1b[42m" in rendered  # green background
    assert rendered.count(ColoredBar.COLOUR_RESET) == 1


def test_colored_bar_blended_segment_glyph_not_full_or_empty():
    """The blend glyph must reflect the split, not collapse to a solid
    full block or a blank - that would silently erase one of the two
    statuses being represented."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[("red", "green", 0.5)])
    rendered = f"{bar}"
    for stripped_char in (ColoredBar.UTF[0], ColoredBar.UTF[-1]):
        assert stripped_char not in rendered


def test_colored_bar_blend_fraction_clamped_away_from_edges():
    """Even a near-vanishing minority (or majority) must still show a hint
    of its color - the glyph index is clamped so neither side of a
    genuinely mixed segment fully disappears."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[("red", "green", 0.01)])
    rendered = f"{bar}"
    assert "\x1b[31m" in rendered
    assert "\x1b[42m" in rendered
    assert ColoredBar.UTF[1] in rendered  # clamped to the smallest non-empty glyph


def test_colored_bar_blend_ignored_for_ascii_charset():
    """ASCII has no eighths-glyph staircase to blend with, so a blended
    segment must fall back to its winner color alone."""
    bar = ColoredBar(
        1.0, default_len=1, charset=ColoredBar.ASCII,
        segment_colours=[("red", "green", 0.5)],
    )
    rendered = f"{bar}"
    assert "\x1b[31m" in rendered
    assert "\x1b[42m" not in rendered


def test_colored_bar_boundary_segment_ignores_blend_fraction():
    """The fractional-edge cell's glyph already encodes overall progress;
    a blended color there must contribute only its winner color, not a
    second sub-cell split (which would conflict with the edge glyph's
    meaning)."""
    bar = ColoredBar(0.5, default_len=2, segment_colours=[None, ("red", "green", 0.5)])
    rendered = f"{bar}"
    assert "\x1b[31m" in rendered
    assert "\x1b[42m" not in rendered


def test_colored_bar_blend_uncolored_runner_up_uses_reverse_video():
    """An uncolored (`None`) runner-up means "terminal default foreground",
    which has no background escape. Without special handling the glyph's
    empty part shows the terminal *background* - a visible hole in the
    bar. Reverse video with the winner as background must be used
    instead, so the empty part takes the default foreground."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[("red", None, 0.5)])
    rendered = f"{bar}"
    assert rendered == f"{ColoredBar.REVERSE}\x1b[41m{ColoredBar.UTF[4]}{ColoredBar.COLOUR_RESET}"


def test_colored_bar_blend_uncolored_runner_up_hex_winner():
    bar = ColoredBar(1.0, default_len=1, segment_colours=[("#ff0000", None, 0.5)])
    rendered = f"{bar}"
    assert ColoredBar.REVERSE in rendered
    assert "\x1b[48;2;255;0;0m" in rendered


def test_colored_bar_blend_both_uncolored_renders_full_block():
    """Two uncolored statuses look identical; a partial glyph would only
    leave a hole, so the segment must render as a plain full block."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[(None, None, 0.5)])
    assert f"{bar}" == ColoredBar.UTF[-1]


def test_colored_bar_blend_uncolored_winner_keeps_fg_bg_path():
    """An uncolored winner is fine as-is (default foreground on the
    glyph, runner-up as background) - no reverse video needed."""
    bar = ColoredBar(1.0, default_len=1, segment_colours=[(None, "green", 0.5)])
    rendered = f"{bar}"
    assert ColoredBar.REVERSE not in rendered
    assert "\x1b[42m" in rendered
