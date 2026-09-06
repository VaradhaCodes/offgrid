#!/usr/bin/env bash
# Side-by-side demo video: camera footage (left) + the phone's screen recording (right), aligned on the SYNC beep.
#
# Usage: tools/compose_video.sh cam.mp4 screen.mp4 <offset_s> [out.mp4]
#   offset_s  seconds to delay the SCREEN recording relative to the camera (positive = screen starts later in the timeline).
#             Find it from the SYNC beeps: the app plays three tones at START, at band entry and at band exit; both recordings
#             capture them (camera mic / screen recorder "Media" sound). offset = t_beep(camera) - t_beep(screen).
#   Optional: tools/compose_video.sh --beeps file.mp4   prints the loudest onsets in the first minutes to locate the beeps.
set -euo pipefail
if [ "${1:-}" = "--beeps" ]; then
  f="$2"; shift 2
  # onsets above -20 dB within 0.25 s windows; the three SYNC tones show as three spikes 240 ms apart
  ffmpeg -hide_banner -loglevel error -i "$f" -af "astats=metadata=1:reset=1:length=0.1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" -f null - 2>/dev/null \
    | awk '/pts_time/ {t=$0; sub(/.*pts_time:/, "", t)} /RMS_level/ {v=$0; sub(/.*=/, "", v); if (v+0 > -20) printf "%.2f s  %s dB\n", t, v}' | head -60
  exit 0
fi
CAM="$1"; SCREEN="$2"; OFF="$3"; OUT="${4:-out.mp4}"
# both scaled to 1080 px tall and stacked; the screen recording (portrait 1080x2316) becomes 504 px wide next to a 1920 px camera frame
ffmpeg -hide_banner -y -i "$CAM" -itsoffset "$OFF" -i "$SCREEN" \
  -filter_complex "[0:v]scale=-2:1080,setsar=1[a];[1:v]scale=-2:1080,setsar=1[b];[a][b]hstack=inputs=2[v]" \
  -map "[v]" -map 0:a? -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "$OUT"
echo "wrote $OUT"
