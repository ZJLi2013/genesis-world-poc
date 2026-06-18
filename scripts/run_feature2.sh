#!/usr/bin/env bash
# feature2 runner: 悬臂垂坠 + bending_compliance 扫描，验证 compliance 物性标定单调性。
set -uo pipefail
export PYOPENGL_PLATFORM=egl

BACKEND="${1:-amdgpu}"
OUT="output/feature2"
mkdir -p "$OUT"
LOG="$OUT/run.log"
echo "=== feature2 run @ $(date -u) backend=$BACKEND ===" | tee "$LOG"

# 搭圆柱：强制曲率，bending_compliance 才有判别力。硬→外鼓(half_width 大、bottom_z 高)，软→贴合。
for B in 1e-10 1e-6 1e-3 1e-1; do
  TAG="cyl_b${B}"
  echo "--- over-cylinder bending=$B ---" | tee -a "$LOG"
  python3 scripts/21_cloth_over_cylinder.py --backend "$BACKEND" --bending "$B" --stretch 1e-8 \
    --size 0.4 --rho 1.0 --steps 1500 --render-every 300 --out "$OUT/$TAG" 2>&1 | tee -a "$LOG"
done

echo "=== feature2 done @ $(date -u) ===" | tee -a "$LOG"
echo "--- metrics ---" | tee -a "$LOG"
grep -a cyl-metric "$LOG" | tee -a "$LOG"
