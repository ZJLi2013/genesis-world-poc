# Issue for genesis-nyx — ✅ 已提交 [#18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18)

Target repo: `Genesis-Embodied-AI/genesis-nyx`
Title: **[Feature/Support] Nyx aborts on AMD (ROCm/RADV) at scene.build() — hard `cuInit` dependency despite Vulkan ray-tracing engine**

---

## Summary

Nyx's renderer engine appears to be Vulkan-based (SPIR-V/Slang shaders, `VK_KHR_ray_tracing_pipeline` / `acceleration_structure`), which AMD RDNA GPUs support natively via RADV. However `gs-nyx-plugin` aborts during `scene.build()` on an AMD-only host because it hard-requires the NVIDIA CUDA driver (`libcuda.so` → `cuInit`), with no ROCm/HIP or CPU-readback fallback.

Is AMD support planned, or is there a supported way to run Nyx without a CUDA device (e.g. a Vulkan-only / HIP external-memory interop, or a CPU tensor readback path for `cam.read().rgb`)?

## Environment

- GPU: AMD Radeon AI PRO R9700 (RDNA4, gfx1201), 2× visible
- OS/driver: Ubuntu 24.04, Mesa 25.2.8 RADV, ROCm 7.2
- Container base: `rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12_pytorch_release_2.10.0`
- `genesis-world==1.2.1`, `gs-nyx-plugin==0.1.4`, `gs-nyx==0.1.3`, `torch 2.10.0+rocm7.2.3`
- Headless (offscreen), devices mounted: `--device=/dev/kfd --device=/dev/dri`

## What works on AMD

- Genesis itself initializes fine: `Running on [AMD Radeon Graphics] with backend gs.amdgpu`.
- Vulkan sees the GPU with hardware ray tracing (`vulkaninfo --summary`):
  ```
  deviceName = AMD Radeon Graphics (RADV GFX1201)   deviceType = DISCRETE_GPU
  driverName = radv   apiVersion = 1.4.318
  rayTracingPipeline / accelerationStructure: present
  ```

## Failure

Minimal splat render (a `LightFieldAsset(GaussianField)` on a `NyxCameraOptions`, `scene.build()` then `scene.step()`):

```
[Genesis] Running on [AMD Radeon Graphics] with backend gs.amdgpu.
[Genesis] Building scene <...>...
Failed to load NVIDIA CUDA driver library: libcuda.so: cannot open shared object file
<SIGABRT / exit 134>
```

Diagnosis: providing an empty `libcuda.so.1` stub changes the error to
`Failed to load CUDA driver symbol: cuInit`, i.e. Nyx genuinely calls the CUDA
Driver API at init (not a soft/optional probe). Removing the bundled
`libOpenImageDenoise_device_cuda.so` does not help, so the dependency is in the
Nyx core init path, not the OIDN denoiser backend.

## Ask

1. Confirm whether AMD (ROCm/HIP) is on the roadmap for Nyx.
2. If the CUDA use is only for the GPU→tensor handoff of `cam.read().rgb`, would a
   Vulkan external-memory→HIP interop or a host/CPU readback path be feasible, so
   the Vulkan RT engine can be used on RADV-capable AMD GPUs?
3. Any current workaround to run Nyx headless on an AMD-only node?

Happy to test patches on RDNA4 (gfx1201) hardware.
