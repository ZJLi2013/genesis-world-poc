#!/usr/bin/env bash
# Build vk_gaussian_splatting on AMD RADV/RDNA4 (no NVIDIA runtime).
# Consolidated repro for feature2 (see docs/exp/part2-exp.md E1).
# Runs inside the `vkgs_build` container (base: genesis-nyx-amd:latest).
# Usage:  docker exec -i vkgs_build bash -s < build_vkgs_amd.sh
#
# The AMD/USE_DLSS=OFF source fixes now live in our fork branch (rdna4_support),
# not as sed patches here -- see docs/upstream/ for the matching upstream issues.
set -euo pipefail

REPO=/work/vk_gaussian_splatting
FORK=https://github.com/ZJLi2013/vk_gaussian_splatting.git
BRANCH=rdna4_support
SDK_VER=1.4.350.1                       # >= 1.4.341 required by nvpro_core2 static_assert
SDK_DIR=/opt/${SDK_VER}

# ---- 1. build deps (Ubuntu) ----
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  cmake git curl ca-certificates pkg-config \
  libvulkan-dev vulkan-tools glslang-tools glslang-dev spirv-tools libshaderc-dev \
  libx11-dev libxcb1-dev libxcb-keysyms1-dev libxcursor-dev libxi-dev \
  libxinerama-dev libxrandr-dev libxxf86vm-dev libtbb-dev zlib1g-dev

# ---- 2. LunarG Vulkan SDK 1.4.350 (Ubuntu ships only 1.3.275; too old) ----
if [ ! -d "$SDK_DIR" ]; then
  cd /opt
  [ -f vulkan_sdk.tar.xz ] || curl -sL -o vulkan_sdk.tar.xz \
    "https://sdk.lunarg.com/sdk/download/${SDK_VER}/linux/vulkan_sdk.tar.xz"
  tar xf vulkan_sdk.tar.xz
fi
# shellcheck disable=SC1090
source "${SDK_DIR}/setup-env.sh"

# ---- 3. shaderc shared lib symlink (build looks for libshaderc_shared.so) ----
L=/usr/lib/x86_64-linux-gnu
ln -sf "$L/libshaderc.so.1" "$L/libshaderc_shared.so"
ldconfig

# ---- 4. clone our fork branch (carries the AMD/USE_DLSS=OFF fixes) ----
[ -d "$REPO" ] || git clone --recursive -b "$BRANCH" "$FORK" "$REPO"
cd "$REPO"

# ---- 5. configure + build ----
rm -rf build
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DUSE_DLSS=OFF -DDISABLE_DEFAULT_SCENE=ON
cmake --build build -j"$(nproc)"

echo "== done: $(ls -la _bin/Release/vk_gaussian_splatting) =="
