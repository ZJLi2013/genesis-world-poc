# Genesis Nyx 3DGS renderer on AMD RDNA4 (R9700 / gfx1201).
#
# Key insight: Nyx's renderer is Vulkan-based (VK_KHR_ray_tracing_pipeline +
# acceleration_structure), NOT CUDA/OptiX. RDNA4 gets hardware ray tracing via
# Mesa 25 RADV, so Nyx runs on AMD despite the "NVIDIA required" note in the
# upstream README.
#
# Base gives: Ubuntu 24.04 (apt Mesa 25 RADV), Python 3.12, ROCm torch (for the
# DLPack tensor handoff of cam.read().rgb).
#
# Built image (committed): genesis-nyx-amd:latest
#
# Run (headless is fine — RADV renders offscreen via /dev/dri, no X/Wayland):
#   docker run --rm --device=/dev/kfd --device=/dev/dri --group-add video \
#     --ipc=host --security-opt seccomp=unconfined \
#     -v $(pwd):/work -w /work genesis-nyx-amd:latest \
#     python render_kitchen.py --ply assets/rustic_kitchen_2m.ply --out out/kitchen.png
#
# Verify the GPU is visible to Vulkan (expect "AMD Radeon Graphics (RADV GFX1201)"):
#   docker run --rm --device=/dev/kfd --device=/dev/dri genesis-nyx-amd:latest vulkaninfo --summary

FROM rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12_pytorch_release_2.10.0

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      mesa-vulkan-drivers vulkan-tools libvulkan1 libglfw3 \
      xvfb \
 && rm -rf /var/lib/apt/lists/*

# genesis-world 1.2.1 + Nyx plugin. Does not pull torch (keeps ROCm torch);
# numpy resolves to 2.x, compatible with torch 2.10.
RUN pip install --no-cache-dir "genesis-world==1.2.1" gs-nyx-plugin
