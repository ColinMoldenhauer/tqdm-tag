import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from tqdm import TqdmWarning, tqdm
from tqdm.std import Bar
from tqdm.utils import (
    FormatReplace,
    _is_ascii,
    disp_len,
    disp_trim,
)

# TODO: what happens in non-color environments?
# TODO: how to work together with `color` argument?
# TODO: include error/warning in default text part of tqdm info (e.g. 90/100 [1/1])

__all__ = ["Tag", "TqdmTag", "TqdmErrorTag", "ColoredBar"]


@dataclass
class Tag:
    """A named status tag with an optional color and status value.

    Parameters
    ----------
    name : str
        Tag identifier, also used as display label in the legend.
    color : str, optional
        Color for bar segments and legend swatch. Accepts named colors
        (`"red"`, `"yellow"`, …) or hex strings (`"#ff4444"`).
        Defaults to `None` (inherits bar color).
    status : int, optional
        Integer used to rank tags when multiple items share one bar segment.
        Higher values take priority with `reduce_op=max` (the default).
        Auto-assigned (next available integer) if omitted.
    """
    name: str
    color: Optional[str] = None
    status: Optional[int] = None


class TqdmTag(tqdm):

    # dtype backing the preallocated per-item status array (used when `total`
    # is known); status values must fit within its range - see
    # `_warn_if_status_out_of_range`.
    _STATUS_DTYPE = np.uint8
    _STATUS_DTYPE_INFO = np.iinfo(_STATUS_DTYPE)

    def __init__(
        self,
        iterable=None,
        total=None,
        colour=None,
        default_status=0,
        default_tag_name="default",
        tags=None,
        initial_status=None,
        reduce_op=max,
        reduce_ignore_default=False,
        legend=False,
        legend_format=None,
        legend_show_default=False,
        **kwargs,
    ):
        """A `tqdm` progress bar whose segments are colored by per-item tags.

        Each iteration starts at `default_status`; calling `tag()` during the
        loop body records a different status for the current item. When the
        bar is rendered, each displayed segment's color is derived from the
        statuses of the items it represents (via `reduce_op`), using the
        color registered for the corresponding tag.

        Parameters
        ----------
        iterable : iterable, optional
            Iterable to decorate, same as in `tqdm`.
        total : int, optional
            Expected number of iterations, same as in `tqdm`.
        colour : str, optional
            Default bar colour, used for items still at `default_status`.
        default_status : int, optional
            Status value assigned to every item before `tag()` is called
            on it (default `0`).
        default_tag_name : str, optional
            Name of the implicit tag representing `default_status`, used
            as its key in `tag_to_status`/`tag_to_color` and its label in
            the legend (default `"default"`). Change this if `"default"`
            collides with a tag name you want to use, or to give the
            untagged state a more descriptive label.
        tags : list of Tag, optional
            Tags to pre-register, in addition to the implicit
            `default_tag_name` tag. Tags used for the first time via
            `tag()` are auto-registered.
        initial_status : dict, array-like, or None, optional
            Restores per-item status for a resumed run (paired with
            `initial`), so a bar started mid-way still shows accurate
            history for the items it didn't itself iterate. Values are raw
            status ints (as in `Tag.status`/`tag_to_status`, not tag names)
            and must already be registered - via `tags` - before use here.
            Accepts:
              - a `dict` of `{index: status}`, for a sparse subset of items;
              - a 2D array-like of shape `(2, N)`: row 0 is indices, row 1
                is the matching statuses, also for a sparse subset;
              - a 1D array-like of shape `(total,)`, giving every item's
                status directly (requires `total` to be known).
            Defaults to `None` (every item starts at `default_status`).
        reduce_op : callable, optional
            Reduction applied to the statuses within a bar segment to pick
            the status (and therefore color) representing that segment
            (default `max`, i.e. highest-status tag wins).
        reduce_ignore_default : bool, optional
            If `True`, exclude items still at `default_status` from the
            reduction within a segment, unless the whole segment is at
            `default_status` (default `False`).
        legend : bool, optional
            If `True`, print a legend line below the bar showing tag counts
            (default `False`).
        legend_format : callable or str, optional
            Customizes the legend line. A callable is invoked as
            `legend_format(tag_counts, tag_to_color) -> str` for full control.
            A `str` is used as a template with a `{legend}` placeholder for
            the default swatch rendering (e.g. `"tags: {legend}"`). Defaults
            (`None`) to the built-in colored swatch format, unchanged.
        legend_show_default : bool, optional
            If `True`, include `default_tag_name` in the legend, with its
            count derived as processed items minus the sum of all other
            tag counts (default `False`, matching the previous behavior of
            never showing it).
        **kwargs
            Forwarded to `tqdm.__init__`.
        """

        # replicate tqdm's total parsing
        if total is None and iterable is not None:
            try:
                total = len(iterable)
            except (TypeError, AttributeError):
                total = None
        if total == float("inf"):
            # Infinite iterations, behave same as unknown
            total = None

        # initialize the status for each iterable item
        # needs to be set before super().__init__ because it calls overridden format_dict()
        if total is not None:
            # number of iterable items known -> preallocate, filled with
            # default_status so items in an `initial` prefix (never written
            # to by __iter__, since it starts enumerating at `initial`)
            # render as "untagged" rather than whatever status happens to be 0,
            # unless overwritten below by `initial_status`
            self._item_status = np.full(total, default_status, dtype=self._STATUS_DTYPE)
        else:
            # number unknown -> use python's dynamic sized list
            self._item_status = []
        # set early (super().__init__ will set it again to the same value)
        # so _set_status - used by _apply_initial_status below - can already
        # tell preallocated-array from dynamic-list mode
        self.total = total

        # build tag mappings from the tags list
        self.default_status = default_status
        self.default_tag_name = default_tag_name
        self.tag_to_status = {default_tag_name: default_status}
        self.tag_to_color = {default_tag_name: colour}

        if tags is not None:
            for t in tags:
                next_status = max(self.tag_to_status.values()) + 1
                new_status = t.status if t.status is not None else next_status
                self._warn_if_status_out_of_range(new_status)
                self.tag_to_status[t.name] = new_status
                if t.color is not None:
                    self.tag_to_color[t.name] = t.color

        self.status_to_tag = {val: key for key, val in self.tag_to_status.items()}

        self.reduce_op = reduce_op
        self.reduce_ignore_default = reduce_ignore_default
        self._legend = legend
        self._legend_format = legend_format
        self._legend_show_default = legend_show_default
        # pre-registered tags start at count 0 so the legend is visible
        # from the start, rather than only appearing once a tag is first used
        self._tag_counts = {name: 0 for name in self.tag_to_status if name != default_tag_name}
        self._legend_active = False  # tracks whether a legend line has been written
        self._iterating = False  # set by __iter__; tag() uses this to detect manual (non-iterable) usage

        # apply before super().__init__(), which - unless disable=True - ends by
        # calling self.refresh() itself; seeding _item_status/_tag_counts after
        # that point would leave the very first rendered frame uncolored until
        # the next refresh
        self._apply_initial_status(initial_status)

        super().__init__(iterable=iterable, total=total, colour=colour, **kwargs)

    def _resolve_initial_status_pairs(self, initial_status):
        """Normalize `initial_status` into a list of `(index, status)` pairs.

        Accepts a `dict`, a sparse `(2, N)` array-like (indices, statuses),
        or a dense `(total,)` array-like - see `__init__`'s docstring.
        """
        if isinstance(initial_status, dict):
            return list(initial_status.items())

        arr = np.asarray(initial_status)
        if arr.ndim == 2:
            if arr.shape[0] != 2:
                raise ValueError(
                    "initial_status as a 2D array must have shape (2, N): "
                    f"row 0 = indices, row 1 = statuses; got shape {arr.shape}"
                )
            return list(zip(arr[0].tolist(), arr[1].tolist()))
        if arr.ndim == 1:
            if self.total is not None and len(arr) != self.total:
                raise ValueError(
                    "initial_status as a 1D array must have length total "
                    f"({self.total}); got length {len(arr)}. Use a dict or "
                    "a (2, N) array instead to set a subset of items."
                )
            return list(enumerate(arr.tolist()))
        raise ValueError(
            "initial_status must be a dict, or a 1D/2D array-like; got "
            f"an array with ndim={arr.ndim}"
        )

    def _apply_initial_status(self, initial_status):
        """Seed `_item_status` (and the legend's tag counts) from `initial_status`."""
        if initial_status is None:
            return

        pairs = self._resolve_initial_status_pairs(initial_status)

        # validate every entry before writing any of them, so a bad entry
        # doesn't leave `_item_status` partially updated
        for idx, status in pairs:
            if status not in self.status_to_tag:
                raise ValueError(
                    f"initial_status references unknown status {status!r} "
                    f"at index {idx}; register it first via the `tags` argument"
                )

        for idx, status in pairs:
            self._set_status(idx, status)
            tag_name = self.status_to_tag[status]
            if self._legend and tag_name != self.default_tag_name:
                self._tag_counts[tag_name] = self._tag_counts.get(tag_name, 0) + 1

    def __iter__(self):
        """Iterate over the wrapped iterable, resetting each item's status.

        Before yielding each item, `_current_item_idx` is set and its status
        is reset to `default_status`, so a fresh item that isn't explicitly
        `tag()`-ed still renders with the default color. `_current_item_idx`
        is kept as its own counter - distinct from `self.n` - since it must
        always be exactly the 0-based position of the item currently being
        tagged, regardless of `self.n`'s own semantics (which can start at a
        non-zero `initial`, be mutated by user code, or lag behind `n` for
        display-throttling reasons).

        The reset is skipped for a slot that already holds a non-default
        status. This matters for out-of-order iterables (e.g.
        `concurrent.futures.as_completed`), where `i` is completion order,
        not the item's true position - the loop body tags the true slot via
        `tag(..., index=true_idx)` instead of relying on `i`. Since `i` and
        `true_idx` are drawn from the same `range(total)`, `i` will
        eventually collide with some earlier item's `true_idx`; without the
        guard, that coincidence would reset an already-tagged item back to
        `default_status` for no reason related to the item at slot `i`
        itself.

        Drives `self.iterable` directly and manages `self.n` via explicit
        `update()` calls, rather than delegating to `tqdm.__iter__`'s
        generator, so that breaking out of the loop right after tagging the
        current item still counts it. `tqdm.__iter__` only advances `n` in
        code positioned *after* its own `yield`, which a `break` skips
        entirely (Python throws `GeneratorExit` at the suspended `yield`);
        worse, its `finally` unconditionally does `self.n = n`, overwriting
        `self.n` with that stale, un-incremented count on close - so even
        wrapping `super().__iter__()` and patching `self.n` up afterwards
        would just get clobbered. Owning the `try`/`finally` around our own
        `yield` and calling `update(1)` unconditionally - on normal
        resumption and on early `break` alike - avoids that entirely and
        keeps the just-tagged item's colored segment visible on the final
        bar.
        """
        self._iterating = True
        try:
            # start=self.initial so items are tagged at their absolute position
            # (matching preallocated `_item_status`) rather than a 0-based
            # position within the remaining iterable, when resuming via `initial`.
            # tqdm.__init__ returns early (without setting self.initial) when
            # disable=True, so fall back to self.n, which it sets either way
            initial = getattr(self, "initial", self.n)
            for i, item in enumerate(self.iterable, start=initial):
                self._current_item_idx = i
                current = self._get_status(i)
                if current is None or current == self.default_status:
                    self._set_status(i, self.default_status)
                try:
                    yield item
                finally:
                    self.update(1)
        finally:
            self._iterating = False
            self.close()

    def __iter__old(self):
        """Iterate over the wrapped iterable, resetting each item's status.

        Before yielding each item, its status is set to `default_status`
        so that a fresh item that isn't explicitly `tag()`-ed still
        renders with the default color.

        Manages `self.n` via explicit `update()` calls (rather than
        delegating to `tqdm.__iter__`'s generator) so that breaking out of
        the loop right after tagging the current item still counts it:
        `tqdm.__iter__` only advances `n` in code positioned *after* its
        `yield`, which a `break` skips entirely (Python throws
        `GeneratorExit` at the suspended `yield`) - leaving the just-tagged
        item's colored segment past the render boundary and invisible on
        the final bar, even though its status was already recorded.
        """
        try:
            for i, item in enumerate(self.iterable):
                # record status for this iteration as default
                self._set_status(i, self.default_status)
                self._current_item_idx = i

                print("i", i)
                print("n", self.n)

                try:
                    # yield the actual item
                    yield item
                finally:
                    # runs on normal resumption *and* on an early `break`
                    # (via GeneratorExit), so `n` always reflects this item
                    self.update(1)
        finally:
            self.close()

    # main API
    def tag(self, tag, color="none", status=None, index=None):
        """Record an item's status.

        In manual (non-iterable) usage - i.e. no `for x in pbar` loop driving
        `__iter__` - there's no notion of a "current item" for `tag()` to
        target, and nothing that would otherwise advance the bar. `tag()`
        falls back to `self.n` (which, absent an `__iter__`-driven counter,
        correctly identifies the item about to complete) and calls
        `update(1)` itself, so calling `tag()` alone both records the status
        and advances the bar by one - do not also call `.update()` yourself
        for that same item, or it will be counted twice. This auto-advance
        is skipped whenever `index` is given - see below.

        Parameters
        ----------
        tag : str or Tag
            A `Tag` object or a tag name string referencing a previously
            defined tag.
        color : str, optional
            Override the tag's color for this call. Ignored when `"none"`
            (the default sentinel).
        status : int, optional
            Override the tag's status integer. Only used the first time
            a new tag name is registered.
        index : int, optional
            Item slot to tag, overriding the current item (`self.n` in
            manual mode, `_current_item_idx` while iterating). `tag()`
            never advances the bar when `index` is given - it always
            targets an already-accounted-for slot, not a new item - so
            call it as many times as needed without affecting `n`. Two
            uses:
              - Retrying in manual mode: overwrite a previously tagged
                item's status (e.g. flip it from `"error"` to `"success"`
                once a retry succeeds) without double-counting it.
              - Out-of-order iterables (e.g. `concurrent.futures.
                as_completed`), where the true slot for a completed item
                has to be looked up (e.g. via a `future -> index` dict)
                rather than assumed from iteration/completion order.
            Works the same whether or not `total` is known: `_set_status`
            pads any gap up to `index` with `default_status` either way -
            in the preallocated array (`total` known) it's already
            default-filled, in the dynamic list (`total` unknown) it
            extends the list.
        """
        if isinstance(tag, Tag):
            if color == "none" and tag.color is not None:
                color = tag.color
            if status is None:
                status = tag.status
            tag = tag.name

        manual_mode = not self._iterating
        if index is not None:
            i = index
        elif manual_mode:
            i = self.n
        else:
            i = self._current_item_idx

        # register new tag name on first use
        if tag not in self.tag_to_status:
            new_status = status if status is not None else max(self.tag_to_status.values()) + 1
            self._warn_if_status_out_of_range(new_status)
            self.tag_to_status[tag] = new_status
            self.status_to_tag[new_status] = tag

        if color != "none":
            self.tag_to_color[tag] = color

        self._set_status(i, self.tag_to_status[tag])

        if self._legend and tag != self.default_tag_name:
            self._tag_counts[tag] = self._tag_counts.get(tag, 0) + 1

        if manual_mode and index is None:
            self.update(1)

    def _warn_if_status_out_of_range(self, status):
        """Warn if `status` won't fit in the preallocated per-item status array.

        When `total` is known, `_item_status` is a fixed `_STATUS_DTYPE`
        numpy array (`uint8` by default) for memory efficiency; writing a
        status outside its range raises `OverflowError` in `_set_status`.
        Warn as soon as such a status is registered, rather than leaving the
        user to debug a cryptic numpy error once the item is actually tagged.
        """
        if self.total is None:
            return
        dtype_info = self._STATUS_DTYPE_INFO
        if not (dtype_info.min <= status <= dtype_info.max):
            warnings.warn(
                f"status {status} is outside the {self._STATUS_DTYPE.__name__} "
                f"range ({dtype_info.min}-{dtype_info.max}) used to store "
                "per-item status when `total` is known; tagging an item "
                "with it will raise an OverflowError",
                TqdmWarning,
                stacklevel=3,
            )

    # helper functions for coloring functionality
    def _get_status(self, idx):
        """Return the currently recorded status for item `idx`.

        Returns
        -------
        int or None
            The recorded status, or `None` if `idx` hasn't been recorded
            yet (only possible when `total` is unknown).
        """
        if self.total is not None:
            return self._item_status[idx]
        if idx < len(self._item_status):
            return self._item_status[idx]
        return None

    def _set_status(self, idx, status):
        """Record `status` for item `idx` in `self._item_status`.

        Writes into the preallocated array when `total` is known,
        otherwise appends to (or overwrites within) the dynamic list.
        """
        if self.total is not None:
            self._item_status[idx] = status
        else:
            if idx < len(self._item_status):
                self._item_status[idx] = status
            else:
                # pad any gap before idx (e.g. an `initial` prefix that was
                # never iterated in this run) with default_status, so the
                # list stays index-aligned with absolute item position
                self._item_status.extend(
                    [self.default_status] * (idx - len(self._item_status))
                )
                self._item_status.append(status)

    @staticmethod
    def _get_colors(
        n_segments,
        item_status,
        status_to_tag,
        tag_to_color,
        default_status,
        reduce_op=max,
        reduce_ignore_default=False,
        **kwargs,
    ):
        """Compute a color (or blended fg/bg color pair) per bar segment.

        Splits `item_status` into `n_segments` chunks (or, if there are
        fewer items than segments, maps each item to one or more
        segments) and reduces the statuses within each chunk via
        `reduce_op`. A chunk holding a single status - the common case
        when `n_segments >= len(item_status)` - resolves to a plain
        color. A chunk holding multiple distinct statuses is reduced
        *twice*: once over every status to find the "winner", and once
        more over whatever's left to find the "runner-up" - so e.g. with
        the default `reduce_op=max`, the highest-status item's tag still
        wins the segment (as before), but the next-highest status
        present is also captured rather than discarded. The pair is
        returned as `(winner_color, runner_up_color, winner_fraction)`
        so `ColoredBar` can render the segment's single character as a
        proportional blend (foreground = winner, background = runner-up)
        instead of flattening the chunk to one color and losing whatever
        else was in it.

        Parameters
        ----------
        n_segments : int
            Number of bar segments to color.
        item_status : sequence of int
            Status recorded for each iterated item so far.
        status_to_tag : dict
            Maps status integer to tag name.
        tag_to_color : dict
            Maps tag name to color.
        default_status : int
            Status value considered "untagged"; used by
            `reduce_ignore_default`.
        reduce_op : callable, optional
            Reduction applied to the statuses in a segment (default `max`).
        reduce_ignore_default : bool, optional
            If `True`, exclude `default_status` items from the reduction
            within a segment unless the whole segment is at
            `default_status` (default `False`).
        **kwargs
            Ignored; allows passing a superset dict (e.g. `format_dict`)
            via `**` unpacking.

        Returns
        -------
        list
            One entry per segment, length `n_segments`. Each entry is
            either a color (or `None`) for a segment with a single
            effective status, or a `(winner_color, runner_up_color,
            winner_fraction)` tuple for a segment whose items span
            multiple statuses.
        """
        if len(item_status) == 0:
            return [None] * n_segments

        # shared linear boundary (floor(k * total / n_segments)) for both branches
        # below, matching the `filled` boundary ColoredBar.__format__ derives from
        # the same frac - two independently-computed boundaries would otherwise
        # disagree, displacing the rendered segment from the true progress edge
        edges = (np.arange(n_segments + 1) * len(item_status)) // n_segments
        if n_segments > len(item_status):  # more segments to draw than items -> multiple segments per item
            spl = [np.array([item_status[edges[i]]]) for i in range(n_segments)]
        else:  # more elements than segments -> each segment may contain different stati
            spl = [item_status[edges[i]:edges[i + 1]] for i in range(n_segments)]

        def resolve_color(status):
            return tag_to_color.get(status_to_tag[status], None)

        def reduce_segment(sp):
            if reduce_ignore_default:
                # filter default status from current split
                sp = [s_ for s_ in sp if s_ != default_status]
                # avoid empty splits due to filtering
                if not sp: sp = [default_status]

            winner = reduce_op(sp)
            remaining = [s_ for s_ in sp if s_ != winner]
            if not remaining:
                # single effective status in this segment -> flat color, as before
                return resolve_color(winner)

            # hierarchical reduce: apply the same op to whatever's left after
            # removing the winner, so a second status survives instead of
            # being silently outvoted
            runner_up = reduce_op(remaining)
            winner_fraction = (len(sp) - len(remaining)) / len(sp)
            return resolve_color(winner), resolve_color(runner_up), winner_fraction

        return [reduce_segment(spl_) for spl_ in spl]

    @property
    def format_dict(self):
        """Public API for read-only member access."""
        if self.disable and not hasattr(self, "unit"):
            return defaultdict(
                lambda: None,
                {"n": self.n, "total": self.total, "elapsed": 0, "unit": "it"},
            )
        if self.dynamic_ncols:
            self.ncols, self.nrows = self.dynamic_ncols(self.fp)
        return {
            "n": self.n,
            "total": self.total,
            "elapsed": self._time() - self.start_t if hasattr(self, "start_t") else 0,
            "ncols": self.ncols,
            "nrows": self.nrows,
            "prefix": self.desc,
            "ascii": self.ascii,
            "unit": self.unit,
            "unit_scale": self.unit_scale,
            "rate": self._ema_dn() / self._ema_dt() if self._ema_dt() else None,
            "bar_format": self.bar_format,
            "postfix": self.postfix,
            "unit_divisor": self.unit_divisor,
            "initial": self.initial,
            "colour": self.colour,
            "item_status": self._item_status,
            "status_to_tag": self.status_to_tag,
            "default_status": self.default_status,
            "tag_to_color": self.tag_to_color,
            "reduce_op": self.reduce_op,
            "reduce_ignore_default": self.reduce_ignore_default,
        }

    @staticmethod
    def format_meter(
        n,
        total,
        elapsed,
        ncols=None,
        prefix="",
        ascii=False,
        unit="it",
        unit_scale=False,
        rate=None,
        bar_format=None,
        postfix=None,
        unit_divisor=1000,
        initial=0,
        colour=None,
        **extra_kwargs,
    ):
        """Return a string-based progress bar given some parameters.

        Overrides `tqdm.format_meter` to render `{bar}` as a `ColoredBar`
        with segments colored by item status.

        Parameters
        ----------
        n : int or float
            Number of finished iterations.
        total : int or float, optional
            Expected total number of iterations. `None` disables ETA.
        elapsed : float
            Seconds elapsed since start.
        ncols : int, optional
            Total output width. Dynamically resizes `{bar}` to fit.
            `0` prints only stats, no bar.
        prefix : str, optional
            Prefix message; available as `{desc}` in bar_format.
        ascii : bool or str, optional
            Use ASCII characters instead of Unicode smooth blocks.
        unit : str, optional
            Iteration unit label (default `"it"`).
        unit_scale : bool or int or float, optional
            If `True` or `1`, apply SI prefixes (k, M, …). Any other
            non-zero number scales `total` and `n` directly.
        rate : float, optional
            Manual iteration rate override (default: `n / elapsed`).
        bar_format : str, optional
            Custom bar string. Default: `"{l_bar}{bar}{r_bar}"` where
            `l_bar = "{desc}: {percentage:3.0f}%|"` and
            `r_bar = "| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]"`.
            Available placeholders: `l_bar`, `bar`, `r_bar`, `n`, `n_fmt`,
            `total`, `total_fmt`, `percentage`, `elapsed`, `elapsed_s`,
            `ncols`, `nrows`, `desc`, `unit`, `rate`, `rate_fmt`,
            `rate_noinv`, `rate_noinv_fmt`, `rate_inv`, `rate_inv_fmt`,
            `postfix`, `unit_divisor`, `remaining`, `remaining_s`, `eta`.
        postfix : str, optional
            Additional stats appended after the bar.
        unit_divisor : float, optional
            Divisor used when `unit_scale` is active (default: `1000`).
        initial : int or float, optional
            Initial counter value (default: `0`).
        colour : str, optional
            Bar colour, e.g. `"green"` or `"#00ff00"`.
        **extra_kwargs
            Forwarded from `TqdmTag.format_dict`
            (`item_status`, `status_to_tag`, `tag_to_color`, …).

        Returns
        -------
        str
            Formatted meter string ready for display.
        """

        # sanity check: total
        if total and n >= (total + 0.5):  # allow float imprecision (#849)
            total = None

        # apply custom scale if necessary
        if unit_scale and unit_scale not in (True, 1):
            if total:
                total *= unit_scale
            n *= unit_scale
            if rate:
                rate *= unit_scale  # by default rate = self.avg_dn / self.avg_dt
            unit_scale = False

        elapsed_str = tqdm.format_interval(elapsed)

        # if unspecified, attempt to use rate = average speed
        # (we allow manual override since predicting time is an arcane art)
        if rate is None and elapsed:
            rate = (n - initial) / elapsed
        inv_rate = 1 / rate if rate else None
        format_sizeof = tqdm.format_sizeof
        rate_noinv_fmt = (
            ((format_sizeof(rate) if unit_scale else f"{rate:5.2f}") if rate else "?")
            + unit
            + "/s"
        )
        rate_inv_fmt = (
            (
                (format_sizeof(inv_rate) if unit_scale else f"{inv_rate:5.2f}")
                if inv_rate
                else "?"
            )
            + "s/"
            + unit
        )
        rate_fmt = rate_inv_fmt if inv_rate and inv_rate > 1 else rate_noinv_fmt

        if unit_scale:
            n_fmt = format_sizeof(n, divisor=unit_divisor)
            total_fmt = (
                format_sizeof(total, divisor=unit_divisor) if total is not None else "?"
            )
        else:
            n_fmt = str(n)
            total_fmt = str(total) if total is not None else "?"

        try:
            postfix = ", " + postfix if postfix else ""
        except TypeError:
            pass

        remaining = (total - n) / rate if rate and total else 0
        remaining_str = tqdm.format_interval(remaining) if rate else "?"
        try:
            eta_dt = (
                datetime.now() + timedelta(seconds=remaining)
                if rate and total
                else datetime.fromtimestamp(0, timezone.utc)
            )
        except OverflowError:
            eta_dt = datetime.max

        # format the stats displayed to the left and right sides of the bar
        if prefix:
            # old prefix setup work around
            bool_prefix_colon_already = prefix[-2:] == ": "
            l_bar = prefix if bool_prefix_colon_already else prefix + ": "
        else:
            l_bar = ""

        r_bar = f"| {n_fmt}/{total_fmt} [{elapsed_str}<{remaining_str}, {rate_fmt}{postfix}]"

        # Custom bar formatting
        # Populate a dict with all available progress indicators
        format_dict = {
            # slight extension of self.format_dict
            "n": n,
            "n_fmt": n_fmt,
            "total": total,
            "total_fmt": total_fmt,
            "elapsed": elapsed_str,
            "elapsed_s": elapsed,
            "ncols": ncols,
            "desc": prefix or "",
            "unit": unit,
            "rate": inv_rate if inv_rate and inv_rate > 1 else rate,
            "rate_fmt": rate_fmt,
            "rate_noinv": rate,
            "rate_noinv_fmt": rate_noinv_fmt,
            "rate_inv": inv_rate,
            "rate_inv_fmt": rate_inv_fmt,
            "postfix": postfix,
            "unit_divisor": unit_divisor,
            "colour": colour,
            # plus more useful definitions
            "remaining": remaining_str,
            "remaining_s": remaining,
            "l_bar": l_bar,
            "r_bar": r_bar,
            "eta": eta_dt,
            **extra_kwargs,
        }

        # total is known: we can predict some stats
        if total:
            # fractional and percentage progress
            frac = n / total
            percentage = frac * 100

            l_bar += f"{percentage:3.0f}%|"

            if ncols == 0:
                return l_bar[:-1] + r_bar[1:]

            format_dict.update(l_bar=l_bar)
            if bar_format:
                format_dict.update(percentage=percentage)

                # auto-remove colon for empty `{desc}`
                if not prefix:
                    bar_format = bar_format.replace("{desc}: ", "")
            else:
                bar_format = "{l_bar}{bar}{r_bar}"

            full_bar = FormatReplace()
            nobar = bar_format.format(bar=full_bar, **format_dict)
            if not full_bar.format_called:
                return nobar  # no `{bar}`; nothing else to do

            # Formatting progress bar space available for bar's display
            n_segments = max(1, ncols - disp_len(nobar)) if ncols else 10
            segment_colours = TqdmTag._get_colors(n_segments, **format_dict)
            full_bar = ColoredBar(
                frac,
                n_segments,
                charset=ColoredBar.ASCII if ascii is True else ascii or ColoredBar.UTF,
                segment_colours=segment_colours,
            )
            if not _is_ascii(full_bar.charset) and _is_ascii(bar_format):
                bar_format = str(bar_format)
            res = bar_format.format(bar=full_bar, **format_dict)
            return disp_trim(res, ncols) if ncols else res

        elif bar_format:
            # user-specified bar_format but no total
            l_bar += "|"
            format_dict.update(l_bar=l_bar, percentage=0)
            full_bar = FormatReplace()
            nobar = bar_format.format(bar=full_bar, **format_dict)
            if not full_bar.format_called:
                return nobar
            n_segments = max(1, ncols - disp_len(nobar)) if ncols else 10
            segment_colours = TqdmTag._get_colors(n_segments, **format_dict)
            full_bar = ColoredBar(
                0,
                max(1, ncols - disp_len(nobar)) if ncols else 10,
                segment_colours=segment_colours,
                charset=ColoredBar.BLANK,
            )
            res = bar_format.format(bar=full_bar, **format_dict)
            return disp_trim(res, ncols) if ncols else res
        else:
            # no total: no progressbar, ETA, just progress stats
            return (
                f"{(prefix + ': ') if prefix else ''}"
                f"{n_fmt}{unit} [{elapsed_str}, {rate_fmt}{postfix}]"
            )

    def _legend_tag_counts(self):
        """Return the tag counts to render in the legend.

        `self._tag_counts` never tracks `default_tag_name` directly - items
        are only counted there when explicitly `tag()`-ed (or seeded via
        `initial_status`) with a non-default tag. When `legend_show_default`
        is enabled, the default tag's count is derived instead of tracked:
        every processed item (`self.n`) that isn't accounted for by another
        tag's count must still be at `default_status`.

        Returns
        -------
        dict
            `self._tag_counts`, plus `default_tag_name` mapped to its
            derived count if `legend_show_default` is enabled.
        """
        if not self._legend_show_default:
            return self._tag_counts
        default_count = max(self.n - sum(self._tag_counts.values()), 0)
        return {self.default_tag_name: default_count, **self._tag_counts}

    def _default_legend(self):
        """Render one colored swatch and count per tag, status-ordered.

        Returns
        -------
        str
            The default swatch-based legend content, with no surrounding
            formatting applied.
        """
        parts = []
        _tmp = ColoredBar(0, 1)
        swatch_char = "#" if self.ascii else "■"
        sorted_tags = sorted(
            self._legend_tag_counts().items(),
            key=lambda kv: self.tag_to_status.get(kv[0], 0),
        )
        for tag_name, count in sorted_tags:
            color = self.tag_to_color.get(tag_name)
            swatch = swatch_char
            ansi = _tmp._resolve_colour(color)
            if ansi:
                swatch = f"{ansi}{swatch_char}{ColoredBar.COLOUR_RESET}"
            parts.append(f"{swatch} {tag_name}: {count}")
        return "   ".join(parts)

    def _format_legend(self):
        """Build the legend line shown below the bar.

        `legend_format` controls the result: a callable is invoked as
        `legend_format(tag_counts, tag_to_color) -> str` for full control;
        a `str` is treated as a template and formatted with a single
        `{legend}` placeholder holding the default swatch rendering (e.g.
        `"tags: {legend}"`); `None` (the default) uses the default swatch
        rendering as-is.

        Returns
        -------
        str
            The formatted legend line.
        """
        if callable(self._legend_format):
            return self._legend_format(self._legend_tag_counts(), self.tag_to_color)
        if isinstance(self._legend_format, str):
            return self._legend_format.format(legend=self._default_legend())
        return self._default_legend()

    def display(self, msg=None, pos=None):
        """Render the bar, then print the legend line beneath it if enabled.

        Overrides `tqdm.display`. The legend is only written to a TTY
        (it would corrupt output otherwise) and the cursor is returned
        to the bar's line afterward so subsequent bar updates overwrite
        in place.

        Parameters
        ----------
        msg : str, optional
            Pre-formatted status message, same as in `tqdm.display`.
        pos : int, optional
            Line offset for multi-bar displays, same as in `tqdm.display`.
        """
        super().display(msg=msg, pos=pos)
        if not self._legend:
            return
        if not getattr(self.fp, "isatty", lambda: False)():
            return
        legend = self._format_legend()
        if not legend:
            return
        width = self.ncols or 80
        # move to legend line, write (padded to clear old content), return to bar line
        self.fp.write(f"\n{legend:<{width}}\x1b[A\r")
        self.fp.flush()
        self._legend_active = True

    def close(self):
        """Close the bar, then move past the legend line if one was drawn.

        Overrides `tqdm.close`.
        """
        # tqdm.close() is idempotent (guarded by self.disable); mirror that
        # guard here so a redundant close (e.g. via __del__ once the last
        # reference to this bar is dropped) doesn't write a second stray
        # newline into whatever's rendering next on the same stream
        already_closed = self.disable
        super().close()
        # super().close() ends with \n that lands the cursor on the legend line;
        # write one more \n so subsequent output starts below the legend
        if not already_closed and self._legend_active:
            self.fp.write("\n")
            self.fp.flush()


class TqdmErrorTag(TqdmTag):
    """A `TqdmTag` with `"warn"` and `"error"` tags pre-registered.

    Adds convenience `warn()`/`error()` methods on top of the generic
    `tag()` API. `"error"` has a higher status than `"warn"`, so with the
    default `reduce_op=max` a segment containing both is shown as an error.
    """

    WARN  = Tag("warn",  color="yellow", status=1)
    ERROR = Tag("error", color="red",    status=2)

    def __init__(self, *args, tags=None, **kwargs):
        """Initialize with the `warn`/`error` tags prepended to `tags`.

        Parameters
        ----------
        *args
            Forwarded to `TqdmTag.__init__`.
        tags : list of Tag, optional
            Additional tags to register alongside `WARN` and `ERROR`.
        **kwargs
            Forwarded to `TqdmTag.__init__`.
        """
        base = [self.WARN, self.ERROR]
        super().__init__(*args, tags=base + list(tags or []), **kwargs)

    def warn(self, **kwargs):
        """Mark the current item with the `"warn"` tag.

        Parameters
        ----------
        **kwargs
            Forwarded to `TqdmTag.tag` (e.g. `color`, `status` overrides).
        """
        self.tag("warn", **kwargs)

    def error(self, **kwargs):
        """Mark the current item with the `"error"` tag.

        Parameters
        ----------
        **kwargs
            Forwarded to `TqdmTag.tag` (e.g. `color`, `status` overrides).
        """
        self.tag("error", **kwargs)


class ColoredBar(Bar):
    """Drop-in replacement for `tqdm.std.Bar` supporting per-segment color.

    Behaves like `Bar` when formatted (supports the same `format_spec`
    suffixes `a`/`u`/`b` and numeric width), but colors each rendered
    block according to `segment_colours` using ANSI escape codes.
    """

    ASCII = " 123456789#"
    UTF = " " + "".join(map(chr, range(0x258F, 0x2587, -1)))
    BLANK = "  "
    COLOUR_RESET = "\x1b[0m"
    COLOUR_RGB = "\x1b[38;2;%d;%d;%dm"
    COLOUR_RGB_BG = "\x1b[48;2;%d;%d;%dm"
    COLOURS = {
        "BLACK": "\x1b[30m",
        "RED": "\x1b[31m",
        "GREEN": "\x1b[32m",
        "YELLOW": "\x1b[33m",
        "BLUE": "\x1b[34m",
        "MAGENTA": "\x1b[35m",
        "CYAN": "\x1b[36m",
        "WHITE": "\x1b[37m",
    }

    def __init__(self, frac, default_len=10, charset=UTF, segment_colours=None):
        """Create a bar renderer for the given fraction complete.

        Parameters
        ----------
        frac : float
            Fraction of the bar that is filled, in `[0, 1]`. Values
            outside the range are clamped with a warning.
        default_len : int, optional
            Number of segments to render when `__format__` isn't given
            an explicit width (default `10`).
        charset : str, optional
            String of characters from emptiest to fullest block, used
            to render partial segments (default `UTF`).
        segment_colours : sequence, optional
            Color (name, hex string, or `None`), or `(winner_color,
            runner_up_color, winner_fraction)` for a blended segment, per
            segment - see `TqdmTag._get_colors`. Indexed in render order.
        """
        if not 0 <= frac <= 1:
            warnings.warn("clamping frac to range [0, 1]", TqdmWarning, stacklevel=2)
            frac = max(0, min(1, frac))
        assert default_len > 0
        self.frac = frac
        self.default_len = default_len
        self.charset = charset
        self.segment_colours = segment_colours

    def _resolve_colour(self, value, background=False):
        """Resolve a color name or hex string to an ANSI escape sequence.

        Parameters
        ----------
        value : str or None
            A key in `COLOURS` (case-insensitive), a `"#rrggbb"` hex
            string, or `None`.
        background : bool, optional
            If `True`, resolve to the background-color escape instead of
            the foreground one (default `False`). Used to render blended
            segments, where the runner-up status colors the "unfilled"
            part of the segment's glyph rather than the glyph itself.

        Returns
        -------
        str or None
            The ANSI escape sequence, or `None` if `value` is `None` or
            unrecognized.
        """
        if value is None:
            return None
        if isinstance(value, str):
            if value.upper() in self.COLOURS:
                code = self.COLOURS[value.upper()]
                # foreground codes are "\x1b[3Nm"; background is the same
                # code with the family digit swapped 3 -> 4
                return code[:2] + "4" + code[3:] if background else code
            if value.startswith("#") and len(value) == 7:
                rgb = tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
                return (self.COLOUR_RGB_BG if background else self.COLOUR_RGB) % rgb
        return None

    def __format__(self, format_spec):
        """Render the bar to a string, coloring each segment.

        Supports the same `format_spec` as `tqdm.std.Bar`: an optional
        trailing `a`/`u`/`b` selects the ASCII/UTF/BLANK charset, and a
        leading integer sets the bar width (negative values subtract
        from `default_len`).

        A segment whose `segment_colours` entry is a `(winner_color,
        runner_up_color, winner_fraction)` tuple - see
        `TqdmTag._get_colors` - renders as a single glyph split
        proportionally between the two colors (foreground = winner,
        background = runner-up), using the UTF charset's eighths-block
        staircase. Only available with the UTF charset; ASCII/BLANK fall
        back to the winner color alone.

        Parameters
        ----------
        format_spec : str
            Format specification, e.g. `""`, `"20"`, `"20a"`, `"-5u"`.

        Returns
        -------
        str
            The rendered, ANSI-colored bar.
        """
        # --- parse format spec exactly like tqdm ---
        if format_spec:
            _type = format_spec[-1].lower()
            charset = {"a": self.ASCII, "u": self.UTF, "b": self.BLANK}.get(
                _type, self.charset
            )
            if _type in "aub":
                format_spec = format_spec[:-1]

            N_BARS = int(format_spec) if format_spec else self.default_len
            if N_BARS < 0:
                N_BARS += self.default_len
        else:
            charset = self.charset
            N_BARS = self.default_len

        # --- compute filled bar length ---
        nsyms = len(charset) - 1
        filled, remainder = divmod(int(self.frac * N_BARS * nsyms), nsyms)

        bar = []

        # --- render full blocks ---
        segment_colours = self.segment_colours
        # sub-cell blending needs the full eighths glyph staircase (UTF); ASCII
        # digits and the blank charset have no equivalent, so those charsets
        # fall back to the segment's winner color only, same as before
        blend_eligible = charset == self.UTF
        for i in range(filled):
            spec = segment_colours[i]
            sym = charset[-1]
            if blend_eligible and isinstance(spec, tuple):
                winner_colour, runner_up_colour, winner_fraction = spec
                fg = self._resolve_colour(winner_colour)
                bg = self._resolve_colour(runner_up_colour, background=True)
                # clamp away from 0/nsyms so neither status ever fully
                # vanishes from a segment that's genuinely mixed
                k = min(max(round(winner_fraction * nsyms), 1), nsyms - 1)
                sym = charset[k]
                bar.append(f"{fg or ''}{bg or ''}{sym}{self.COLOUR_RESET}")
            else:
                colour = self._resolve_colour(spec[0] if isinstance(spec, tuple) else spec)
                bar.append(f"{colour}{sym}{self.COLOUR_RESET}" if colour else sym)

        # --- fractional block ---
        if filled < N_BARS:
            sym = charset[remainder]
            spec = segment_colours[filled]
            # this glyph's shape already encodes the overall progress fraction
            # (`remainder`), so a blended segment here only contributes its
            # winner color, not a second sub-cell split
            colour = self._resolve_colour(spec[0] if isinstance(spec, tuple) else spec)
            bar.append(f"{colour}{sym}{self.COLOUR_RESET}" if colour else sym)
            bar.extend(charset[0] * (N_BARS - filled - 1))

        return "".join(bar)
