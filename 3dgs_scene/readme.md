# 3dgs_scene — Genesis Nyx 3DGS 渲染验证

> **Status: 🚧 BLOCKED（AMD 视角）** — Nyx 渲染引擎(Vulkan 硬件光追)在 RDNA4 上兼容，但闭源发行版在 `scene.build()` 期硬依赖 NVIDIA `libcuda.so`/`cuInit`，AMD 无回退直接 SIGABRT，且无源码不可自修。已提上游 issue：[genesis-nyx #18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18)，等官方是否支持 AMD（HIP/Vulkan-only interop 或 CPU 回读）。

验证 Genesis World 1.0 对 **3D Gaussian Splatting（3DGS）渲染**的支持程度（对应上游 [issue #1358](https://github.com/Genesis-Embodied-AI/genesis-world/issues/1358)，已由 **Nyx plugin** 在 Genesis 1.0 中解决）。

## 背景结论（速查）

- Genesis 的 3DGS 渲染走 **Nyx**：一个 GPU 路径追踪器，作为 camera sensor 挂进 scene（`scene.add_sensor(NyxCameraOptions(...))`）。
- splat 作为 **`LightFieldAsset`**（`type=GaussianField`，`uri=*.ply`）挂到 `NyxCameraOptions.light_fields`，`scene.build()` 收集、每次 `scene.step()` 渲染，`cam.read().rgb` 取帧。
- splat 是 **pre-lit**（view-dependent 颜色已烘焙），HDRI env map 只需照亮同帧的 mesh 几何。

### 关键更正：Nyx 引擎是 Vulkan，不是 CUDA

官方 README 写「需 NVIDIA GPU + CUDA 12.9+ / driver 575+」，**但那是官方「支持/验证」声明，不是引擎的技术依赖**。实测 `gs_nyx` 二进制符号（见 [part1-exp E0](docs/exp/part1-exp.md)）：

| 类别 | 命中 | 结论 |
|---|---|---|
| Vulkan 栈 | `vulkan=78 spirv=770 VK_KHR=13 raytracing/acceleration slang` + ldd 依赖 `libvulkan.so.1` | 渲染核心 = **Vulkan 硬件光追 + SPIR-V/Slang** |
| CUDA compute | `cudart=0 nvrtc=0 optix=0 cublas=0`（仅 `cuda=39` interop 串） | **无** CUDA kernel / OptiX |
| 张量输出 | `dlpack=9`（+ `torch=3`） | 走 **DLPack**（框架无关），非硬绑 torch-CUDA |

- wheel `gs_nyx-*-manylinux_2_34_x86_64.whl` 是**纯 manylinux 包，无 cuda tag** → 可 pip 装到 AMD 机器。

### AMD 视角结论：引擎兼容，但发行版被 libcuda 卡住

分两层看（证据 [part1-exp](docs/exp/part1-exp.md)）：

**✅ 引擎层可行**：AMD 9700 容器内（Mesa 25 RADV）`vulkaninfo --summary` 枚举到 **`AMD Radeon Graphics (RADV GFX1201)`** = `DISCRETE_GPU`，Vulkan 1.4.318，`rayTracingPipeline`/`accelerationStructure` 齐全 → RDNA4 有 Nyx 所需的 Vulkan 硬件光追（前提：容器 **Mesa ≥ 24.3**；旧 Mesa 23.2 只见 llvmpipe CPU）。Genesis 1.2.1 本体也能在 `gs.amdgpu` 上 init。

**❌ 但发行版开箱不可用且不可自修**：`gs-nyx-plugin` 的 `scene.build()` 在 AMD 上因 **加载不到 `libcuda.so` 直接 SIGABRT**（排除了 OIDN CUDA 后端）。用空 libcuda stub 验证，报错变为 **`Failed to load CUDA driver symbol: cuInit`** → Nyx **真的调 CUDA Driver API**（Vulkan↔CUDA 外部内存交接），非 triton 噪声。核心 `.so` **闭源**（genesis-nyx repo 仅 docs+examples），无法重指到 HIP → 自行修复此路不通。

> **headless 不影响**：RADV 通过 `/dev/dri/renderD*` 离屏渲染，不需要 X/Wayland。libcuda 才是拦路石。

## 实验镜像（后续 base）

**`genesis-nyx-amd:latest`**（9700 节点本地，`docker commit` 得到；可复现见 [`Dockerfile`](./Dockerfile)）：

- base `rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12_pytorch_release_2.10.0`
- 加 `mesa-vulkan-drivers`(25.2.8 RADV) + `vulkan-tools` + `libvulkan1` + `libglfw3`
- pip `genesis-world==1.2.1` + `gs-nyx-plugin`；自带 `torch 2.10.0+rocm7.2.3`（HIP，接 Nyx DLPack 输出）

```bash
# 起容器（headless，挂 GPU 设备 + 工作目录）
docker run --rm --device=/dev/kfd --device=/dev/dri --group-add video \
  --ipc=host --security-opt seccomp=unconfined -v $(pwd):/work -w /work \
  genesis-nyx-amd:latest \
  python render_kitchen.py --ply assets/rustic_kitchen_2m.ply --out out/kitchen.png
```

## 实验节点

- **AMD R9700 节点**（`10.161.176.9`）：4× Radeon AI PRO R9700（RDNA4/gfx1201），host RADV Mesa 25.2.8，Python 3.12 → **目标平台**，用 `genesis-nyx-amd:latest` 容器。
- ~~NVIDIA 4090 节点~~：官方支持路径，本轮不再推进（AMD 才是目标）。

## 实验数据

worldlabs Marble 示例资产「Rustic kitchen with natural light」的 Gaussian splat PLY：

- 500k splats（smoke）：`assets/rustic_kitchen_500k.ply`
- 2M splats（正式）：`assets/rustic_kitchen_2m.ply`
- 坐标系：worldlabs 默认 OpenCV（+x left, +y down, +z forward）；导入 Genesis（Z-up）需做 OpenCV→OpenGL/Z-up 旋转。

## 开发方法

feature-dev-pipeline：backlog（`docs/overall_todo.md`）→ 设计+as-built（`docs/features/featureN_*.md`）→ 实现+实验证据（`docs/exp/partN-exp.md`）。
