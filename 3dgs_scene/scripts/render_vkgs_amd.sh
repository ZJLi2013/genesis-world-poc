#!/usr/bin/env bash
# Headless render on RADV/RDNA4 (see docs/exp/part2-exp.md E1/E2).
# KEY: --saveImage must live inside a benchmark SEQUENCE, not as a bare CLI arg
#      (bare arg triggers getColorImage on a null GBuffer before first render -> SIGSEGV).
# Usage: docker exec -i vkgs_build bash -s < render_vkgs_amd.sh
set -euo pipefail
source /opt/1.4.350.1/setup-env.sh
cd /work/vk_gaussian_splatting
BIN=_bin/Release/vk_gaussian_splatting
OUT=/work/out; mkdir -p "$OUT"

# ---- E1: 3 pipelines on a single splat PLY (raster / RT / hybrid) ----
PLY=/work/assets/rustic_kitchen_2m.ply
cat > "$OUT/tiers.cfg" <<EOF
SEQUENCE "raster"
--sequenceframes 200
--pipeline 1
--saveImage $OUT/vkgs_raster.png

SEQUENCE "raytrace"
--sequenceframes 200
--pipeline 2
--saveImage $OUT/vkgs_rt.png

SEQUENCE "hybrid"
--sequenceframes 200
--pipeline 3
--saveImage $OUT/vkgs_hybrid.png
EOF
"$BIN" --benchmark 1 --sequencefile "$OUT/tiers.cfg" --headless 1 \
  --forcegpu 0 --size 1280 720 "$PLY"

# ---- E2: unified mesh + gaussian project (.vkgs) ----
# Windows backslash asset paths are normalized by the loader (fork rdna4_support),
# so the sample project loads directly on Linux -- no path rewrite needed.
cd samples
VKGS=3dgs_winter_house_objects_on_stove_lighting.vkgs
cat > "$OUT/e2.cfg" <<EOF
SEQUENCE "raster_cam2"
--sequenceframes 250
--pipeline 1
--activateCameraPreset 2
--saveImage $OUT/e2_cam2.png
EOF
"$BIN" --benchmark 1 --sequencefile "$OUT/e2.cfg" --headless 1 \
  --forcegpu 0 --size 1280 720 --inputProject "$VKGS"

echo "== outputs =="; ls -la "$OUT"/*_main.png
