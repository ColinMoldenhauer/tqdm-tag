#!/usr/bin/env bash
# Record scripts/demo_run.py with asciinema and convert the result to a GIF with agg.
# See the docstring of scripts/demo_run.py for how to install asciinema and agg.
#
#   scripts/record_demo.sh                  # plain tqdm, then tqdm-tag -> docs/assets/demo.gif
#   scripts/record_demo.sh --side-by-side   # tqdm-tag | plain tqdm -> docs/assets/demo-side-by-side.gif
#   scripts/record_demo.sh --usage          # quick-start example, legend=True | legend=False
#                                           #   -> docs/assets/demo-usage.gif
#
# Side-by-side GIFs are two recordings merged frame by frame into one GIF (needs
# ImageMagick): two separate GIFs on a page each animate on their own clock and drift apart.
#
# Options: --out-dir DIR (default docs/assets)  --cols N  --rows N  --font-size N  -h|--help
set -euo pipefail

side_by_side=0
usage=0
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="$repo/docs/assets"
cols="" rows="" font_size=16

while [[ $# -gt 0 ]]; do
  case "$1" in
    --side-by-side) side_by_side=1 ;;
    --usage)     usage=1 ;;
    --out-dir)   out_dir="$2"; shift ;;
    --cols)      cols="$2"; shift ;;
    --rows)      rows="$2"; shift ;;
    --font-size) font_size="$2"; shift ;;
    -h|--help)   sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

# side-by-side: narrower terminals so each GIF stays readable at half width, and
# just 4 rows (title, bar, legend, final cursor line) so the GIFs carry no empty space
if [[ $side_by_side -eq 1 ]]; then
  cols="${cols:-64}" rows="${rows:-4}"
elif [[ $usage -eq 1 ]]; then
  cols="${cols:-80}" rows="${rows:-3}"  # bar, legend, final cursor line
else
  cols="${cols:-80}" rows="${rows:-14}"
fi
ncols=$((cols - 2))

tools=(asciinema agg)
[[ $side_by_side -eq 1 || $usage -eq 1 ]] && tools+=(convert identify)  # ImageMagick, for hstack
for tool in "${tools[@]}"; do
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

record() {  # record GIF [demo_run args...] -> GIF
  local gif="$1"; shift
  asciinema rec "$tmp/rec.cast" --overwrite \
    -c "python $repo/scripts/demo_run.py --ncols $ncols $*"
  agg --font-size "$font_size" "$tmp/rec.cast" "$gif"
}

hstack() {  # hstack LEFT RIGHT OUT: merge two GIFs frame by frame into one
  # Both recordings run the same workload at the same pace, so agg emits the same
  # number of frames with (near-)identical delays; pair frame i with frame i and
  # keep the left GIF's delays.
  local left="$1" right="$2" out="$3" d="$tmp/hstack" i
  local -a delays args
  mapfile -t delays < <(identify -format "%T\n" "$left")
  local n_right; n_right="$(identify -format "%T\n" "$right" | wc -l)"
  if [[ ${#delays[@]} -ne $n_right ]]; then
    echo "frame counts differ (${#delays[@]} vs $n_right), cannot merge in sync; re-run" >&2
    exit 1
  fi
  rm -rf "$d"; mkdir -p "$d"
  convert "$left" -coalesce "$d/l_%04d.png"
  convert "$right" -coalesce "$d/r_%04d.png"
  for ((i = 0; i < ${#delays[@]}; i++)); do
    printf -v f "%04d" "$i"
    convert "$d/l_$f.png" "$d/r_$f.png" +append +repage "$d/f_$f.png"
    args+=(-delay "${delays[i]}" "$d/f_$f.png")
  done
  convert -loop 0 "${args[@]}" -layers Optimize "$out"
}

if [[ $side_by_side -eq 1 ]]; then
  record "$tmp/tag.gif"   --only tag
  record "$tmp/plain.gif" --only plain
  hstack "$tmp/tag.gif" "$tmp/plain.gif" "$out_dir/demo-side-by-side.gif"
  echo "wrote $out_dir/demo-side-by-side.gif"
elif [[ $usage -eq 1 ]]; then
  record "$tmp/legend.gif"   --only usage
  record "$tmp/nolegend.gif" --only usage --no-legend
  hstack "$tmp/legend.gif" "$tmp/nolegend.gif" "$out_dir/demo-usage.gif"
  echo "wrote $out_dir/demo-usage.gif"
else
  record "$out_dir/demo.gif"
  echo "wrote $out_dir/demo.gif"
fi
