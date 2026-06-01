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
    def __init__(
        self,
        iterable=None,
        total=None,
        colour=None,
        default_status=0,
        tags=None,
        reduce_op=max,
        reduce_ignore_default=False,
        legend=False,
        legend_format=None,
        **kwargs,
    ):
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
            # number of iterable items known -> preallocate
            self._item_status = np.zeros(total, dtype=np.uint8)
        else:
            # number unknown -> use python's dynamic sized list
            self._item_status = []

        # build tag mappings from the tags list
        self.default_status = default_status
        self.tag_to_status = {"default": default_status}
        self.tag_to_color = {"default": colour}

        if tags is not None:
            for t in tags:
                next_status = max(self.tag_to_status.values()) + 1
                self.tag_to_status[t.name] = t.status if t.status is not None else next_status
                if t.color is not None:
                    self.tag_to_color[t.name] = t.color

        self.status_to_tag = {val: key for key, val in self.tag_to_status.items()}

        self.reduce_op = reduce_op
        self.reduce_ignore_default = reduce_ignore_default
        self._legend = legend
        self._legend_format = legend_format
        self._tag_counts = {}
        self._legend_active = False  # tracks whether a legend line has been written

        super().__init__(iterable=iterable, total=total, colour=colour, **kwargs)

    def __iter__(self):
        for i, item in enumerate(super().__iter__()):
            # record status for this iteration as default
            self._set_status(i, self.default_status)
            self._current_item_idx = i

            # yield the actual item
            yield item

    # main API
    def tag(self, tag, color="none", status=None):
        """Record the current item's status.

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
        """
        if isinstance(tag, Tag):
            if color == "none" and tag.color is not None:
                color = tag.color
            if status is None:
                status = tag.status
            tag = tag.name

        i = self._current_item_idx

        # register new tag name on first use
        if tag not in self.tag_to_status:
            new_status = status if status is not None else max(self.tag_to_status.values()) + 1
            self.tag_to_status[tag] = new_status
            self.status_to_tag[new_status] = tag

        if color != "none":
            self.tag_to_color[tag] = color

        self._set_status(i, self.tag_to_status[tag])

        if self._legend and tag != "default":
            self._tag_counts[tag] = self._tag_counts.get(tag, 0) + 1

    # helper function for coloring functionality
    def _set_status(self, idx, status):
        if self.total is not None:
            self._item_status[idx] = status
        else:
            if idx < len(self._item_status):
                self._item_status[idx] = status
            else:
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
        if len(item_status) == 0:
            return [None] * n_segments

        if n_segments > len(item_status):  # more segments to draw than items -> multiple segments per item
            indices = np.linspace(0, len(item_status) - 1e-5, n_segments)
            indices = np.floor(indices).astype(int)
            spl = [np.array([item_status[i]]) for i in indices]
        else:  # more elements than segments -> each segment may contain different stati
            spl = np.array_split(item_status, n_segments)

        # assign
        def reducer(sp):
            if reduce_ignore_default:
                # filter default status from current split
                sp = [s_ for s_ in sp if s_ != default_status]
                # avoid empty splits due to filtering
                if not sp: sp = [default_status]

            return reduce_op(sp)

        segment_status = [reducer(spl_) for spl_ in spl]

        segment_color_name = [status_to_tag[st_] for st_ in segment_status]
        segment_color = [tag_to_color.get(tag_, None) for tag_ in segment_color_name]
        return segment_color

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

    def _format_legend(self):
        if self._legend_format is not None:
            return self._legend_format(self._tag_counts, self.tag_to_color)

        parts = []
        _tmp = ColoredBar(0, 1)
        swatch_char = "#" if self.ascii else "■"
        sorted_tags = sorted(
            self._tag_counts.items(),
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

    def display(self, msg=None, pos=None):
        super().display(msg=msg, pos=pos)
        if not self._legend or not self._tag_counts:
            return
        if not getattr(self.fp, "isatty", lambda: False)():
            return
        legend = self._format_legend()
        width = self.ncols or 80
        # move to legend line, write (padded to clear old content), return to bar line
        self.fp.write(f"\n{legend:<{width}}\x1b[A\r")
        self.fp.flush()
        self._legend_active = True

    def close(self):
        super().close()
        # super().close() ends with \n that lands the cursor on the legend line;
        # write one more \n so subsequent output starts below the legend
        if self._legend_active:
            self.fp.write("\n")
            self.fp.flush()


class TqdmErrorTag(TqdmTag):
    WARN  = Tag("warn",  color="yellow", status=1)
    ERROR = Tag("error", color="red",    status=2)

    def __init__(self, *args, tags=None, **kwargs):
        base = [self.WARN, self.ERROR]
        super().__init__(*args, tags=base + list(tags or []), **kwargs)

    def warn(self, **kwargs):
        self.tag("warn", **kwargs)

    def error(self, **kwargs):
        self.tag("error", **kwargs)


class ColoredBar(Bar):
    ASCII = " 123456789#"
    UTF = " " + "".join(map(chr, range(0x258F, 0x2587, -1)))
    BLANK = "  "
    COLOUR_RESET = "\x1b[0m"
    COLOUR_RGB = "\x1b[38;2;%d;%d;%dm"
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
        if not 0 <= frac <= 1:
            warnings.warn("clamping frac to range [0, 1]", TqdmWarning, stacklevel=2)
            frac = max(0, min(1, frac))
        assert default_len > 0
        self.frac = frac
        self.default_len = default_len
        self.charset = charset
        self.segment_colours = segment_colours

    def _resolve_colour(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            if value.upper() in self.COLOURS:
                return self.COLOURS[value.upper()]
            if value.startswith("#") and len(value) == 7:
                return self.COLOUR_RGB % tuple(
                    int(value[i : i + 2], 16) for i in (1, 3, 5)
                )
        return None

    def __format__(self, format_spec):
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
        # TODO: remove random colors
        segment_colours = self.segment_colours
        for i in range(filled):
            colour = self._resolve_colour(
                segment_colours[i]
            )  # segment_colours[i] if i < len(segment_colours) else None
            sym = charset[-1]
            bar.append(f"{colour}{sym}{self.COLOUR_RESET}" if colour else sym)

        # --- fractional block ---
        if filled < N_BARS:
            sym = charset[remainder]
            colour = self._resolve_colour(segment_colours[filled])
            bar.append(f"{colour}{sym}{self.COLOUR_RESET}" if colour else sym)
            bar.extend(charset[0] * (N_BARS - filled - 1))

        return "".join(bar)
