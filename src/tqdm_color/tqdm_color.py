import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import time

import numpy as np
from tqdm import TqdmDeprecationWarning, TqdmKeyError, TqdmWarning, tqdm
from tqdm.std import EMA, Bar
from tqdm.utils import (
    DisableOnWriteError,
    FormatReplace,
    SimpleTextIOWrapper,
    _is_ascii,
    _screen_shape_wrapper,
    _supports_unicode,
    disp_len,
    disp_trim,
    envwrap,
)



class ErrorTqdm(tqdm):
    DEFAULT_STATUS = 0
    STATUS_MAP = {"default": DEFAULT_STATUS, "warn": 1, "error": 2}
    STATUS_COLORS = {"default": None, "warn": "YELLOW", "error": "RED"}
    STATUS_TO_TAG = {val: key for key, val in STATUS_MAP.items()}
    # _item_status = defaultdict(list)

    # '''
    # override defaults via env vars
    @envwrap("TQDM_", is_method=True, types={'total': float, 'ncols': int, 'miniters': float,
                                             'position': int, 'nrows': int})
    def __init__(self, iterable=None, desc=None, total=None, leave=True, file=None,
                 ncols=None, mininterval=0.1, maxinterval=10.0, miniters=None,
                 ascii=None, disable=False, unit='it', unit_scale=False,
                 dynamic_ncols=False, smoothing=0.3, bar_format=None, initial=0,
                 position=None, postfix=None, unit_divisor=1000, write_bytes=False,
                 lock_args=None, nrows=None, colour=None, delay=0.0, gui=False,
                 **kwargs):
        """see tqdm.tqdm for arguments"""
        if file is None:
            file = sys.stderr

        if write_bytes:
            # Despite coercing unicode into bytes, py2 sys.std* streams
            # should have bytes written to them.
            file = SimpleTextIOWrapper(
                file, encoding=getattr(file, 'encoding', None) or 'utf-8')

        file = DisableOnWriteError(file, tqdm_instance=self)

        if disable is None and hasattr(file, "isatty") and not file.isatty():
            disable = True

        if total is None and iterable is not None:
            try:
                total = len(iterable)
            except (TypeError, AttributeError):
                total = None
        if total == float("inf"):
            # Infinite iterations, behave same as unknown
            total = None

        if total is not None:
            self._item_status = np.zeros(total, dtype=np.uint8)
        else:
            self._item_staus = []

        if disable:
            self.iterable = iterable
            self.disable = disable
            with self._lock:
                self.pos = self._get_free_pos(self)
                self._instances.remove(self)
            self.n = initial
            self.total = total
            self.leave = leave
            return

        if kwargs:
            self.disable = True
            with self._lock:
                self.pos = self._get_free_pos(self)
                self._instances.remove(self)
            raise (
                TqdmDeprecationWarning(
                    "`nested` is deprecated and automated.\n"
                    "Use `position` instead for manual control.\n",
                    fp_write=getattr(file, 'write', sys.stderr.write))
                if "nested" in kwargs else
                TqdmKeyError("Unknown argument(s): " + str(kwargs)))

        # Preprocess the arguments
        if (
            (ncols is None or nrows is None) and (file in (sys.stderr, sys.stdout))
        ) or dynamic_ncols:  # pragma: no cover
            if dynamic_ncols:
                dynamic_ncols = _screen_shape_wrapper()
                if dynamic_ncols:
                    ncols, nrows = dynamic_ncols(file)
            else:
                _dynamic_ncols = _screen_shape_wrapper()
                if _dynamic_ncols:
                    _ncols, _nrows = _dynamic_ncols(file)
                    if ncols is None:
                        ncols = _ncols
                    if nrows is None:
                        nrows = _nrows

        if miniters is None:
            miniters = 0
            dynamic_miniters = True
        else:
            dynamic_miniters = False

        if mininterval is None:
            mininterval = 0

        if maxinterval is None:
            maxinterval = 0

        if ascii is None:
            ascii = not _supports_unicode(file)

        if bar_format and ascii is not True and not _is_ascii(ascii):
            # Convert bar format into unicode since terminal uses unicode
            bar_format = str(bar_format)

        if smoothing is None:
            smoothing = 0

        # Store the arguments
        self.iterable = iterable
        self.desc = desc or ''
        self.total = total
        self.leave = leave
        self.fp = file
        self.ncols = ncols
        self.nrows = nrows
        self.mininterval = mininterval
        self.maxinterval = maxinterval
        self.miniters = miniters
        self.dynamic_miniters = dynamic_miniters
        self.ascii = ascii
        self.disable = disable
        self.unit = unit
        self.unit_scale = unit_scale
        self.unit_divisor = unit_divisor
        self.initial = initial
        self.lock_args = lock_args
        self.delay = delay
        self.gui = gui
        self.dynamic_ncols = dynamic_ncols
        self.smoothing = smoothing
        self._ema_dn = EMA(smoothing)
        self._ema_dt = EMA(smoothing)
        self._ema_miniters = EMA(smoothing)
        self.bar_format = bar_format
        self.postfix = None
        self.colour = colour
        self._time = time
        if postfix:
            try:
                self.set_postfix(refresh=False, **postfix)
            except TypeError:
                self.postfix = postfix

        # Init the iterations counters
        self.last_print_n = initial
        self.n = initial

        # if nested, at initial sp() call we replace '\r' by '\n' to
        # not overwrite the outer progress bar
        with self._lock:
            # mark fixed positions as negative
            self.pos = self._get_free_pos(self) if position is None else -position

        if not gui:
            # Initialize the screen printer
            self.sp = self.status_printer(self.fp)
            if delay <= 0:
                self.refresh(lock_args=self.lock_args)

        # Init the time counter
        self.last_print_t = self._time()
        # NB: Avoid race conditions by setting start_t at the very end of init
        self.start_t = self.last_print_t
    # '''




    def __iter__(self):
        for i, item in enumerate(super().__iter__()):
            # record status for this iteration as default
            self._set_status(i, self.DEFAULT_STATUS)
            self._current_item_idx = i

            # yield the actual item
            yield item


    def _set_status(self, idx, status):
        if self.total:
            self._item_status[idx] = status
        else:
            self._item_status.append(self.DEFAULT_STATUS)

    def _record_status(self, key):
        """Record the current item's status. If key is an integer, it's a direct"""
        n = self._current_item_idx
        if isinstance(key, int):
            status = key
        else:
            status = self.STATUS_MAP.get(key, self.DEFAULT_STATUS)

        self._set_status(n, status)

    def warn(self): self._record_status("warn")
    def error(self): self._record_status("error")

    @staticmethod
    def _get_colors(n_segments, item_status, status_to_tag, tag_to_color, default_status, op=max, **kwargs):

        # more segements to draw than items -> multiple segments per item ()
        if n_segments > len(item_status):
            indices = np.linspace(0, len(item_status)-1e-5, n_segments)
            indices = np.floor(indices).astype(int)
            spl = [np.array([item_status[i]]) for i in indices]
        else:
            spl = np.array_split(item_status, n_segments)

            for spl_ in spl:
                if not spl_.size:
                    print("item_status", item_status, len(item_status))
                    print("n_segments", n_segments)
                    print("spl", spl)
                    raise RuntimeError("Empty slice, how?")


        # assign
        segment_status = [op(
            spl_ if spl_.size else [default_status]
            ) for spl_ in spl]

        segment_color_name = [status_to_tag[st_] for st_ in segment_status]
        segment_color = [tag_to_color[tag_] for tag_ in segment_color_name]
        return segment_color


    @property
    def format_dict(self):
        """Public API for read-only member access."""
        if self.disable and not hasattr(self, 'unit'):
            return defaultdict(lambda: None, {
                'n': self.n, 'total': self.total, 'elapsed': 0, 'unit': 'it'})
        if self.dynamic_ncols:
            self.ncols, self.nrows = self.dynamic_ncols(self.fp)
        return {
            'n': self.n, 'total': self.total,
            'elapsed': self._time() - self.start_t if hasattr(self, 'start_t') else 0,
            'ncols': self.ncols, 'nrows': self.nrows, 'prefix': self.desc,
            'ascii': self.ascii, 'unit': self.unit, 'unit_scale': self.unit_scale,
            'rate': self._ema_dn() / self._ema_dt() if self._ema_dt() else None,
            'bar_format': self.bar_format, 'postfix': self.postfix,
            'unit_divisor': self.unit_divisor, 'initial': self.initial,
            'colour': self.colour,

            'item_status': self._item_status,
            'status_to_tag': self.STATUS_TO_TAG,
            'default_status': self.DEFAULT_STATUS,
            'tag_to_color': self.STATUS_COLORS,
            }


    @staticmethod
    def format_meter(n, total, elapsed, ncols=None, prefix='', ascii=False, unit='it',
                     unit_scale=False, rate=None, bar_format=None, postfix=None,
                     unit_divisor=1000, initial=0, colour=None, **extra_kwargs):
        """
        Return a string-based progress bar given some parameters

        Parameters
        ----------
        n  : int or float
            Number of finished iterations.
        total  : int or float
            The expected total number of iterations. If meaningless (None),
            only basic progress statistics are displayed (no ETA).
        elapsed  : float
            Number of seconds passed since start.
        ncols  : int, optional
            The width of the entire output message. If specified,
            dynamically resizes `{bar}` to stay within this bound
            [default: None]. If `0`, will not print any bar (only stats).
            The fallback is `{bar:10}`.
        prefix  : str, optional
            Prefix message (included in total width) [default: ''].
            Use as {desc} in bar_format string.
        ascii  : bool, optional or str, optional
            If not set, use unicode (smooth blocks) to fill the meter
            [default: False]. The fallback is to use ASCII characters
            " 123456789#".
        unit  : str, optional
            The iteration unit [default: 'it'].
        unit_scale  : bool or int or float, optional
            If 1 or True, the number of iterations will be printed with an
            appropriate SI metric prefix (k = 10^3, M = 10^6, etc.)
            [default: False]. If any other non-zero number, will scale
            `total` and `n`.
        rate  : float, optional
            Manual override for iteration rate.
            If [default: None], uses n/elapsed.
        bar_format  : str, optional
            Specify a custom bar string formatting. May impact performance.
            [default: '{l_bar}{bar}{r_bar}'], where
            l_bar='{desc}: {percentage:3.0f}%|' and
            r_bar='| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, '
              '{rate_fmt}{postfix}]'
            Possible vars: l_bar, bar, r_bar, n, n_fmt, total, total_fmt,
              percentage, elapsed, elapsed_s, ncols, nrows, desc, unit,
              rate, rate_fmt, rate_noinv, rate_noinv_fmt,
              rate_inv, rate_inv_fmt, postfix, unit_divisor,
              remaining, remaining_s, eta.
            Note that a trailing ": " is automatically removed after {desc}
            if the latter is empty.
        postfix  : *, optional
            Similar to `prefix`, but placed at the end
            (e.g. for additional stats).
            Note: postfix is usually a string (not a dict) for this method,
            and will if possible be set to postfix = ', ' + postfix.
            However other types are supported (#382).
        unit_divisor  : float, optional
            [default: 1000], ignored unless `unit_scale` is True.
        initial  : int or float, optional
            The initial counter value [default: 0].
        colour  : str, optional
            Bar colour (e.g. 'green', '#00ff00').

        Returns
        -------
        out  : Formatted meter and stats, ready to display.
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
        rate_noinv_fmt = ((format_sizeof(rate) if unit_scale else f'{rate:5.2f}')
                          if rate else '?') + unit + '/s'
        rate_inv_fmt = (
            (format_sizeof(inv_rate) if unit_scale else f'{inv_rate:5.2f}')
            if inv_rate else '?') + 's/' + unit
        rate_fmt = rate_inv_fmt if inv_rate and inv_rate > 1 else rate_noinv_fmt

        if unit_scale:
            n_fmt = format_sizeof(n, divisor=unit_divisor)
            total_fmt = format_sizeof(total, divisor=unit_divisor) if total is not None else '?'
        else:
            n_fmt = str(n)
            total_fmt = str(total) if total is not None else '?'

        try:
            postfix = ', ' + postfix if postfix else ''
        except TypeError:
            pass

        remaining = (total - n) / rate if rate and total else 0
        remaining_str = tqdm.format_interval(remaining) if rate else '?'
        try:
            eta_dt = (datetime.now() + timedelta(seconds=remaining)
                      if rate and total else datetime.fromtimestamp(0, timezone.utc))
        except OverflowError:
            eta_dt = datetime.max

        # format the stats displayed to the left and right sides of the bar
        if prefix:
            # old prefix setup work around
            bool_prefix_colon_already = (prefix[-2:] == ": ")
            l_bar = prefix if bool_prefix_colon_already else prefix + ": "
        else:
            l_bar = ''

        r_bar = f'| {n_fmt}/{total_fmt} [{elapsed_str}<{remaining_str}, {rate_fmt}{postfix}]'

        # Custom bar formatting
        # Populate a dict with all available progress indicators
        format_dict = {
            # slight extension of self.format_dict
            'n': n, 'n_fmt': n_fmt, 'total': total, 'total_fmt': total_fmt,
            'elapsed': elapsed_str, 'elapsed_s': elapsed,
            'ncols': ncols, 'desc': prefix or '', 'unit': unit,
            'rate': inv_rate if inv_rate and inv_rate > 1 else rate,
            'rate_fmt': rate_fmt, 'rate_noinv': rate,
            'rate_noinv_fmt': rate_noinv_fmt, 'rate_inv': inv_rate,
            'rate_inv_fmt': rate_inv_fmt,
            'postfix': postfix, 'unit_divisor': unit_divisor,
            'colour': colour,
            # plus more useful definitions
            'remaining': remaining_str, 'remaining_s': remaining,
            'l_bar': l_bar, 'r_bar': r_bar, 'eta': eta_dt,
            **extra_kwargs}

        # total is known: we can predict some stats
        if total:
            # fractional and percentage progress
            frac = n / total
            percentage = frac * 100

            l_bar += f'{percentage:3.0f}%|'

            if ncols == 0:
                return l_bar[:-1] + r_bar[1:]

            format_dict.update(l_bar=l_bar)
            if bar_format:
                format_dict.update(percentage=percentage)

                # auto-remove colon for empty `{desc}`
                if not prefix:
                    bar_format = bar_format.replace("{desc}: ", '')
            else:
                bar_format = "{l_bar}{bar}{r_bar}"

            full_bar = FormatReplace()
            nobar = bar_format.format(bar=full_bar, **format_dict)
            if not full_bar.format_called:
                return nobar  # no `{bar}`; nothing else to do

            # Formatting progress bar space available for bar's display
            n_segments = max(1, ncols - disp_len(nobar)) if ncols else 10
            segment_colours = ErrorTqdm._get_colors(n_segments, **format_dict)
            full_bar = ColoredBar(frac,
                           n_segments,
                           charset=ColoredBar.ASCII if ascii is True else ascii or ColoredBar.UTF,
                           colour=colour,
                           segment_colours=segment_colours,
            )
            if not _is_ascii(full_bar.charset) and _is_ascii(bar_format):
                bar_format = str(bar_format)
            res = bar_format.format(bar=full_bar, **format_dict)
            return disp_trim(res, ncols) if ncols else res

        elif bar_format:
            # user-specified bar_format but no total
            l_bar += '|'
            format_dict.update(l_bar=l_bar, percentage=0)
            full_bar = FormatReplace()
            nobar = bar_format.format(bar=full_bar, **format_dict)
            if not full_bar.format_called:
                return nobar
            n_segments = max(1, ncols - disp_len(nobar)) if ncols else 10
            segment_colours = ErrorTqdm._get_colors(n_segments, **format_dict)
            full_bar = ColoredBar(0,
                           max(1, ncols - disp_len(nobar)) if ncols else 10,
                           segment_colours=segment_colours,
                           charset=ColoredBar.BLANK, colour=colour)
            res = bar_format.format(bar=full_bar, **format_dict)
            return disp_trim(res, ncols) if ncols else res
        else:
            # no total: no progressbar, ETA, just progress stats
            return (f'{(prefix + ": ") if prefix else ""}'
                    f'{n_fmt}{unit} [{elapsed_str}, {rate_fmt}{postfix}]')


class ColoredBar(Bar):
    ASCII = " 123456789#"
    UTF = u" " + u''.join(map(chr, range(0x258F, 0x2587, -1)))
    BLANK = "  "
    COLOUR_RESET = '\x1b[0m'
    COLOUR_RGB = '\x1b[38;2;%d;%d;%dm'
    COLOURS = {'BLACK': '\x1b[30m', 'RED': '\x1b[31m', 'GREEN': '\x1b[32m',
               'YELLOW': '\x1b[33m', 'BLUE': '\x1b[34m', 'MAGENTA': '\x1b[35m',
               'CYAN': '\x1b[36m', 'WHITE': '\x1b[37m'}


    def __init__(self, frac, default_len=10, charset=UTF, segment_colours=None, **kwargs):
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
            if value.startswith('#') and len(value) == 7:
                return self.COLOUR_RGB % tuple(
                    int(value[i:i+2], 16) for i in (1, 3, 5)
                )
        return None

    def __format__(self, format_spec):
        # --- parse format spec exactly like tqdm ---
        if format_spec:
            _type = format_spec[-1].lower()
            charset = {'a': self.ASCII, 'u': self.UTF, 'b': self.BLANK}.get(
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
        segment_colours = self.segment_colours or np.random.choice(list(self.COLOURS.values()), filled)
        for i in range(filled):
            colour = self._resolve_colour(
                segment_colours[i] if i < len(segment_colours) else None
            )
            sym = charset[-1]
            bar.append(f"{colour}{sym}{self.COLOUR_RESET}" if colour else sym)

        # --- fractional block ---
        if filled < N_BARS:
            sym = charset[remainder]
            bar.append(sym)
            bar.extend(charset[0] * (N_BARS - filled - 1))

        return "".join(bar)
