#!/usr/bin/env bash
# feature2 runner: 悬臂垂坠 + bending_compliance 扫描，验证 compliance 物性标定单调性。
set -uo pipefail
export PYOPENGL_PLATFORM=egl

BACKEND="${1:-amdgpu}"
OUT="output/feature2"
mkdir -p "$OUT"
LOG="$OUT/run.log"
echo "=== feature2 run @ $(date -u) backend=$BACKEND ===" | tee "$LOG"

# bending_compliance 从硬到软（更宽更硬的区间）；小而轻的布让抗弯能与重力竞争。
for B in 1e-12 1e-9 1e-6 1e-3; do
  TAG="b${B}"
  echo "--- drape bending=$B ---" | tee -a "$LOG"
  python3 scripts/20_cloth_drape.py --backend "$BACKEND" --bending "$B" --stretch 1e-8 \
    --size 0.2 --rho 1.0 --steps 1200 --render-every 300 --out "$OUT/$TAG" 2>&1 | tee -a "$LOG"
done

echo "=== feature2 done @ $(date -u) ===" | tee -a "$LOG"
echo "--- metrics ---" | tee -a "$LOG"
grep -a drape-metric "$LOG" | tee -a "$LOG"
