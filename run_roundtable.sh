#!/usr/bin/env bash
# Run only the roundtable (ARTIST, BUSINESS, TECH). Uses weave_hacks conda env.
set -e
cd "$(dirname "$0")"
conda run -n weave_hacks python -m services.roundtable "$@"
