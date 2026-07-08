# part1 实验记录 — Nyx 渲染 3DGS splat（AMD RDNA4）

设计见 [feature1](../features/feature1_nyx_3dgs_render.md)。

## 总览表

| Exp | 目标 | 状态 | 结论 |
|---|---|---|---|
| E0 | 分析 `gs_nyx` 二进制：CUDA 还是 Vulkan？ | ✅ done | 引擎是 **Vulkan 光追 + SPIR-V/Slang**，无 CUDA kernel；输出走 DLPack |
| E1 | 在 AMD 容器内让 Vulkan 枚举到 RDNA4 GPU + 光追 | ✅ done | Mesa 25 RADV 认出 `GFX1201` DISCRETE_GPU，支持 rayTracingPipeline/accelerationStructure |
| E2 | `docker commit` 出可复现 base 镜像 | ✅ done | `genesis-nyx-amd:latest`（见 [Dockerfile](../../Dockerfile)） |
| E3 | 容器内渲染 rustic kitchen splat 出图 | ❌ blocked | `scene.build()` 缺 `libcuda.so` SIGABRT |
| E3.1 | libcuda stub 判定真伪依赖 | ✅ done | stub 后报 `cuInit` 符号缺失 → **真调 CUDA API，非 triton 噪声；闭源不可自修** |

## 环境

- 节点：AMD 9700（`10.161.176.9`），4× Radeon AI PRO R9700（RDNA4/gfx1201），host RADV Mesa 25.2.8。
- 镜像：`genesis-nyx-amd:latest`（base `rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12_pytorch_release_2.10.0` + Mesa25 + genesis 1.2.1 + gs-nyx-plugin）。
- 工作目录：host `/home/david/zhengjli_3dgs_amd`（`assets/` splat PLY，`out/` 输出），容器挂到 `/work`。

## E0: gs_nyx 二进制 = Vulkan 还是 CUDA？

**背景**：上游 README 称「需 NVIDIA CUDA 12.9+」，与 AMD 目标冲突，需先判断是硬依赖还是官方支持声明。

**方法**：`ldd` + `strings` 扫 `nyx_py_renderer.so` / `nyx_py_sdk.so` 的符号。

**结果**：
- ldd 动态依赖：`libvulkan.so.1`、`libOpenImageDenoise`、`libglfw`；**无** libcuda/libcudart。
- 符号计数：`vulkan=78 spirv=770 VK_KHR=13 raytracing=2 acceleration=6 slang`；`cudart=0 nvrtc=0 optix=0 cublas=0`（`cuda=39` 仅 interop 串）；`dlpack=9 torch=3`。

**结论**：Nyx 渲染核心是 **Vulkan 硬件光追（VK_KHR_ray_tracing_pipeline + acceleration_structure）+ SPIR-V/Slang 着色器**，GPU→张量走 **DLPack**。CUDA 只是 NVIDIA 侧 interop 之一，非引擎硬依赖 → AMD 有戏。

## E1: AMD 容器内 Vulkan 枚举 + 光追

**方法**：在装了 Mesa 25 RADV 的容器里挂 `--device=/dev/kfd --device=/dev/dri`，跑 `vulkaninfo --summary`。

**结果**：
```
deviceName = AMD Radeon Graphics (RADV GFX1201)   deviceType = DISCRETE_GPU   driverName = radv   apiVersion = 1.4.318
rayTracingPipeline hits: 25
accelerationStructure hits: 30
```
- 对照：原 `genesis-amd` 镜像（Mesa 23.2.1）只枚举到 `llvmpipe`(CPU)，认不出 gfx1201。

**结论**：**RDNA4 + Mesa 25 RADV 提供 Vulkan 硬件光追，满足 Nyx 底层需求。** 关键前提是容器 Mesa ≥ 24.3。headless 无影响（RADV 离屏渲染，不需 X/Wayland）。

## E2: 可复现镜像

`docker commit nyx_build genesis-nyx-amd:latest`。版本：genesis 1.2.1 / gs_nyx OK / torch 2.10.0+rocm7.2.3（avail=True）/ numpy 2.3.5。Dockerfile 落库见 `3dgs_scene/Dockerfile`。

## E3: 渲染 rustic kitchen splat

**方案**：容器内 `python render.py --ply assets/rustic_kitchen_2m.ply --out out/kitchen_smoke.png --res 320 240 --spp 2`。关注：Nyx 是否选中 RADV 设备、Vulkan→torch(HIP) 的 DLPack 输出是否成功、出图是否可辨认为厨房。

**结果**（3 次一致）：
```
[Genesis] Running on [AMD Radeon Graphics] with backend gs.amdgpu. Device memory: 29.86 GB.
[Genesis] Genesis initialized. version: 1.2.1
[Genesis] Building scene <...>...
Failed to load NVIDIA CUDA driver library: libcuda.so: cannot open shared object file
<SIGABRT, exit 134>
```
- Genesis 本体在 AMD 上正常 init（gs.amdgpu backend）；abort 发生在 **加了 Nyx sensor 的 `scene.build()`**。
- 排除 OIDN：把 `libOpenImageDenoise_device_cuda.so` 改名后仍在同一处 abort → 不是降噪器的 CUDA 后端。
- `libcuda.so` 引用还来自 torch 依赖的 triton NVIDIA 后端；确切内部触发点（Nyx 的 Vulkan↔CUDA interop vs triton 探测）未完全隔离，但**净结果确定**：无 `libcuda.so` → Nyx build 直接 SIGABRT。

**分析 / 结论**：
- **引擎层可行**（E0/E1 已证）：Nyx 渲染核心是 Vulkan 硬件光追，RDNA4+Mesa25 RADV 支持。
- **但发行版不可行**：`gs-nyx-plugin` 的初始化路径**硬依赖 NVIDIA `libcuda.so`**，AMD 上无回退直接 abort。→ **从 AMD 视角，Genesis 官方 3DGS 渲染（Nyx）当前开箱即用地不可用**，与上游 README「需 NVIDIA CUDA」一致，但根因是 **init 期 CUDA 依赖**（而非渲染算法本身）。

### E3.1 诊断：libcuda stub（判定是否真依赖 CUDA）

**方法**：造空 `libcuda.so.1`（无符号）让 dlopen 成功，重跑 render。

**结果**：报错从 `Failed to load NVIDIA CUDA driver library: libcuda.so` 变为 **`Failed to load CUDA driver symbol: cuInit`**，仍 SIGABRT。

**结论（决定性）**：Nyx **真的调用 CUDA Driver API（`cuInit` 等）**，不是 triton 的无害探测。它在 init 期用 CUDA 驱动 GPU buffer（Vulkan↔CUDA 外部内存交接）。填 stub 只会把崩溃推到下一个 CUDA 调用 —— 背后无 NVIDIA 驱动，无解。

- **是否可自行修复**：❌。核心 `nyx_py_renderer/sdk` 是**闭源二进制**（genesis-nyx repo 仅 docs+examples，源码未公开），无法把 CUDA interop 重指到 HIP/Vulkan-only。
- **最终裁决**：从 AMD 视角，Genesis 官方 3DGS 渲染（Nyx）**当前不可用且不可自修**。渲染引擎(Vulkan RT)本身兼容 RDNA4，卡点纯粹是发行版的 NVIDIA CUDA 运行期绑定。

**Next Step**：
- 已决：向 genesis-nyx 提 issue，请求官方支持 AMD（HIP/Vulkan-only interop 或 CPU 回读的 tensor 输出）。见 `docs/nyx_amd_issue.md` 草稿。
- AMD 侧照相级渲染短期留白；仿真/物理维持既有 PBD/EGL 路径（cloth_sim）。
