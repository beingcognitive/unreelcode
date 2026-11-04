#!/bin/sh
# v3.1 (vertical 1080x1920): concat the shot segments in film order, open 22 frames after the bar-1 strike (the
# first formed figure), with bar 10 already absent (the water shot starts after it), dissolve the last 0.5 s into
# frame 0 so the film loops, mux the master cut identically (splice.py) as AAC, then measure loudness and peak.
set -e
cd "$(dirname "$0")"
FF=$(command -v ffmpeg || echo /opt/homebrew/bin/ffmpeg)
PY=${PY:-python}
$PY splice.py                                                    # -> cache/audio_film.wav (56.767 s)
printf "file 'seg_%s.mp4'\n" s1 s2 s3 s4 s5 s6 water c1 f1 > cache/parts.txt
$FF -y -loglevel error -f concat -safe 0 -i cache/parts.txt -c copy cache/silent.mp4
$FF -y -loglevel error -i cache/silent.mp4 -vf "trim=start_frame=22,setpts=PTS-STARTPTS" -frames:v 1 cache/frame0.png
$FF -y -loglevel error -i cache/silent.mp4 -loop 1 -framerate 30 -t 56.7667 -i cache/frame0.png -i cache/audio_film.wav \
  -filter_complex "[0:v]trim=start_frame=22:end_frame=1725,setpts=PTS-STARTPTS[m];[1:v]format=yuva420p,fade=in:st=56.2667:d=0.5:alpha=1[f];[m][f]overlay=shortest=1,format=yuv420p[v]" \
  -map "[v]" -map 2:a -c:v libx264 -preset slow -crf 17 -r 30 -c:a aac -b:a 256k -frames:v 1703 -movflags +faststart out/film.mp4
$FF -hide_banner -i out/film.mp4 -map 0:a -af ebur128=peak=true -f null - 2>&1 | grep -A20 Summary | grep -E " I:|Peak:|LRA:"
