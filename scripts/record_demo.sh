#!/usr/bin/env bash
# Record scripts/demo_run.py with asciinema and convert the result to GIF(s) with agg.
# See the docstring of scripts/demo_run.py for how to install asciinema and agg.
#
#   scripts/record_demo.sh                  # one GIF: plain tqdm, then tqdm-tag -> docs/assets/demo.gif
#   scripts/record_demo.sh --side-by-side   # two same-size, same-length GIFs for a side-by-side
#                                           #   view -> docs/assets/demo-plain.gif, demo-tag.gif
#
# Options: --out-dir DIR (default docs/assets)  --cols N  --rows N  --font-size N  -h|--help
set -euo pipefail

side_by_side=0
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$repo/docs/assets"
cols="" rows="" font_size=16

while [[ $# -gt 0 ]]; do
  case "$1" in
    --side-by-side) side_by_side=1 ;;
    --out-dir)   out_dir="$2"; shift ;;
    --cols)      cols="$2"; shift ;;
    --rows)      rows="$2"; shift ;;
    --font-size) font_size="$2"; shift ;;
    -h|--help)   sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

# side-by-side: narrower terminals so each GIF stays readable at half width, and
# just 4 rows (title, bar, legend, final cursor line) so the GIFs carry no empty space
if [[ $side_by_side -eq 1 ]]; then
  cols="${cols:-64}" rows="${rows:-4}"
else
  cols="${cols:-80}" rows="${rows:-14}"
fi
ncols=$((cols - 2))

for tool in asciinema agg; do
  command -v "$tool" >/dev/null || { echo "missing: $tool (see scripts/demo_run.py docstring)" >&2; exit 1; }
done

export TERM=xterm-256color LANG=C.UTF-8
mkdir -p "$out_dir"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# asciinema 2.x has no --cols/--rows: it records the current terminal size, so resize
# it for the recording and restore it afterwards (only possible on a real tty).
if [[ -t 0 ]]; then
  old="$(stty size)"
  trap 'stty rows "${old% *}" cols "${old#* }"; rm -rf "$tmp"' EXIT
  stty cols "$cols" rows "$rows"
fi

record() {  # record NAME [demo_run args...] -> $out_dir/NAME.gif
  local name="$1"; shift
  asciinema rec "$tmp/$name.cast" --overwrite \
    -c "python $repo/scripts/demo_run.py --ncols $ncols $*"
  agg --font-size "$font_size" "$tmp/$name.cast" "$out_dir/$name.gif"
  echo "wrote $out_dir/$name.gif"
}

if [[ $side_by_side -eq 1 ]]; then
  record demo-plain --only plain
  record demo-tag   --only tag
else
  record demo
fi
