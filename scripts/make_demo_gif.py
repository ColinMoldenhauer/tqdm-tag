#!/usr/bin/env python
"""Record a real tqdm / tqdm-tag run and render it to an animated GIF.

The demo workload runs in a child process attached to a pseudo-terminal, so
tqdm and tqdm-tag emit exactly the escape sequences they would in a real
terminal. The timestamped output is replayed through a terminal emulator
(pyte) and each frame is drawn with Pillow in a terminal-window style.

    pip install pyte pillow tqdm numpy -e .
    python scripts/make_demo_gif.py                    # -> docs/assets/demo.gif
    python scripts/make_demo_gif.py -o out.gif --fps 20

Requires a monospace TTF with block-element glyphs (JetBrains Mono, DejaVu
Sans Mono, ...); pass --font to choose one explicitly. POSIX only (uses pty).
"""
import argparse
import fcntl
import os
import pty
import random
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

# --------------------------------------------------------------------------
# The workload that is actually recorded (runs in the child process)
# --------------------------------------------------------------------------
N = 60
DELAY = 0.06


def outcomes(n=N, seed=4):
    """Deterministic per-item outcome so both bars see identical results."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        r = rng.random()
        out.append("error" if r < 0.07 else "warn" if r < 0.22 else "ok")
    return out


def child():
    from tqdm import tqdm

    from tqdm_tag import Tag, TqdmTag

    res = outcomes()

    print("\x1b[1;32m$\x1b[0m python process_items.py", flush=True)
    time.sleep(0.8)

    print("\n\x1b[2m# plain tqdm: one color, no idea what went wrong\x1b[0m", flush=True)
    for i in tqdm(range(N), desc="plain tqdm", ncols=78, colour="green"):
        time.sleep(DELAY)
    time.sleep(0.6)

    print("\n\x1b[2m# tqdm-tag: every item colored by its outcome\x1b[0m", flush=True)
    pbar = TqdmTag(
        range(N),
        tags=[Tag("warn", color="#ff8c00"), Tag("error", color="red")],
        colour="green",
        legend=True,
        desc="tqdm-tag  ",
        ncols=78,
    )
    for i in pbar:
        time.sleep(DELAY)
        if res[i] == "warn":
            pbar.tag("warn")
        elif res[i] == "error":
            pbar.tag("error")
    time.sleep(0.1)


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------
def record(cols, rows):
    """Run the child in a pty. Returns [(t, bytes)]."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    env = dict(os.environ, TERM="xterm-256color", PYTHONUNBUFFERED="1")
    env.pop("NO_COLOR", None)
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--child"],
        stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True,
    )
    os.close(slave)
    chunks, t0 = [], time.monotonic()
    while True:
        ready, _, _ = select.select([master], [], [], 0.05)
        if ready:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            chunks.append((time.monotonic() - t0, data))
        elif proc.poll() is not None:
            break
    proc.wait()
    os.close(master)
    if proc.returncode:
        raise SystemExit(f"demo child failed (exit {proc.returncode})")
    return chunks


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
# Catppuccin Mocha, matching the old docs/assets/demo.svg
BG, FG = "#1e1e2e", "#cdd6f4"
TITLEBAR = "#313244"
NAMED = {  # pyte color names -> hex
    "default": None, "black": "#45475a", "red": "#f38ba8", "green": "#a6e3a1",
    "brown": "#f9e2af", "yellow": "#f9e2af", "blue": "#89b4fa",
    "magenta": "#f5c2e7", "cyan": "#94e2d5", "white": "#bac2de",
    "brightblack": "#585b70", "brightred": "#f38ba8", "brightgreen": "#a6e3a1",
    "brightbrown": "#f9e2af", "brightyellow": "#f9e2af", "brightblue": "#89b4fa",
    "brightmagenta": "#f5c2e7", "brightcyan": "#94e2d5", "brightwhite": "#ffffff",
}


def color(c, default):
    if c in NAMED:
        return NAMED[c] or default
    if len(c) == 6:  # pyte gives truecolor / 256-color as "rrggbb"
        try:
            int(c, 16)
            return "#" + c
        except ValueError:
            pass
    return default


def find_font(explicit):
    cands = [explicit] if explicit else []
    cands += [
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/Library/Fonts/JetBrainsMono-Regular.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    raise SystemExit("No monospace font found; pass --font /path/to/font.ttf")


def render(chunks, cols, rows, fps, font_path, size, hold):
    import pyte
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, size)
    cw = round(font.getlength("█"))
    ch = int(size * 1.5)
    pad, bar_h = 18, 34
    W, H = cols * cw + 2 * pad, rows * ch + 2 * pad + bar_h

    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)

    def draw():
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, bar_h], fill=TITLEBAR)
        for k, c in enumerate(("#f38ba8", "#f9e2af", "#a6e3a1")):
            x = 20 + k * 20
            d.ellipse([x - 6, bar_h // 2 - 6, x + 6, bar_h // 2 + 6], fill=c)
        title = "tqdm-tag demo"
        d.text((W / 2, bar_h / 2), title, fill="#a6adc8", font=font, anchor="mm")
        for y in range(rows):
            line = screen.buffer[y]
            for x in range(cols):
                cell = line[x]
                fg, bg = color(cell.fg, FG), color(cell.bg, BG)
                if cell.reverse:
                    fg, bg = bg, fg
                px, py = pad + x * cw, bar_h + pad + y * ch
                if bg != BG:
                    d.rectangle([px, py, px + cw, py + ch], fill=bg)
                if cell.data == "\u2588":  # solid rectangle: no gaps between cells
                    d.rectangle([px, py, px + cw - 1, py + ch - 1], fill=fg)
                elif cell.data.strip():
                    d.text((px, py + (ch - size) // 2 - 2), cell.data, fill=fg, font=font)
        return img

    end = chunks[-1][0] + hold
    frames, durations, last_key, i = [], [], None, 0
    step = 1.0 / fps
    t = 0.0
    while t <= end:
        while i < len(chunks) and chunks[i][0] <= t:
            stream.feed(chunks[i][1].decode("utf-8", "replace"))
            i += 1
        key = tuple(tuple((c.data, c.fg, c.bg, c.reverse) for c in screen.buffer[y].values())
                    for y in range(rows))
        if key == last_key:
            durations[-1] += step
        else:
            frames.append(draw())
            durations.append(step)
            last_key = key
        t += step
    return frames, durations


def save_gif(frames, durations, out):
    # shared palette across frames keeps colors stable and the file small
    first = frames[0].quantize(colors=64, method=2, dither=0)
    pal = [f.quantize(palette=first, dither=0) for f in frames]
    pal[0].save(
        out, save_all=True, append_images=pal[1:],
        duration=[int(d * 1000) for d in durations], loop=0, optimize=True, disposal=1,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--rows", type=int, default=11)
    ap.add_argument("--font", default=None)
    ap.add_argument("--font-size", type=int, default=16)
    ap.add_argument("--hold", type=float, default=3.0, help="seconds to hold the last frame")
    a = ap.parse_args()

    if a.child:
        return child()

    out = Path(a.output) if a.output else Path(__file__).resolve().parent.parent / "docs/assets/demo.gif"
    print("recording ...")
    chunks = record(a.cols, a.rows)
    print(f"  {len(chunks)} output chunks over {chunks[-1][0]:.1f}s")
    print("rendering ...")
    frames, durs = render(chunks, a.cols, a.rows, a.fps, find_font(a.font), a.font_size, a.hold)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_gif(frames, durs, out)
    print(f"wrote {out} ({len(frames)} frames, {out.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
