#!/bin/sh
# Render frames in fresh Blender sessions of CHUNK frames each (a long single session showed a material glitch:
# the house roof turned black after a few hundred frames with persistent data). Resumable.
# usage (from dominoes/): render/render_chunked.sh "<frame list, comma separated>" <outdir> <res> <samples> [extra blender args...]
LIST="$1"; OUT="$2"; RES="$3"; SPP="$4"; shift 4
CHUNK=${CHUNK:-40}
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
TMP=$(mktemp -d)
echo "$LIST" | tr ',' '\n' | split -l "$CHUNK" - "$TMP/chunk_"
for f in "$TMP"/chunk_*; do
  L=$(paste -sd, "$f")
  "$BLENDER" -b --factory-startup --python render/render_frames.py -- \
     --list "$L" --res "$RES" --samples "$SPP" --dir "$OUT" "$@" 2>&1 | grep -E "frames to render|avg\)|Error|Traceback"
done
rm -r "$TMP"
