#!/bin/sh
# Render every 3D frame into cache/raw in fresh Blender sessions of CHUNK frames each. Resumable.
# usage (from pendulum-wave/): ./render.sh [samples, default 32]
# BLENDER: path to Blender 5.1 (default: the macOS app). LOCK: optional lock file shared with other GPU jobs.
cd "$(dirname "$0")"
SPP=${1:-32}
CHUNK=${CHUNK:-48}
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
PY=${PY:-../.venv/bin/python}
N=$($PY -c "import timeline as T; print(T.N_3D)")
for pass in 1 2; do                       # the second pass picks up any chunk that failed
  a=0
  while [ $a -lt $N ]; do
    if [ -n "$LOCK" ]; then RUN="lockf $LOCK"; else RUN=""; fi
    $RUN "$BLENDER" -b --factory-startup --python scene.py -- --a $a --b $((a + CHUNK)) --res 1.0 --samples "$SPP" \
      --dir cache/raw 2>&1 | grep -E "frames to render|avg\)|Error|Traceback"
    a=$((a + CHUNK))
  done
done
echo "rendered $(ls cache/raw | grep -c '^[0-9]*\.png$') of $N frames"
