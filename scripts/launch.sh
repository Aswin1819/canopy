#!/usr/bin/env sh
# Launch the review server with the first working Python 3.8+: python3, then python, then py -3.
# (On Windows, python3 is often the Microsoft Store stub; the version probe skips it.)
HERE="$(cd "$(dirname "$0")" && pwd)"
PROBE='import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'
for cand in "python3" "python" "py -3"; do
  # shellcheck disable=SC2086
  if $cand -c "$PROBE" >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $cand "$HERE/canopy.py" "$@"
  fi
done
echo "canopy: no Python 3.8+ found (tried python3, python, py -3). Install Python from python.org." >&2
exit 2
