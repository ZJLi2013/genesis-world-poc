# 3dgs_scene backlog

验证 Genesis World 1.0 的 3DGS 渲染（Nyx plugin）能力。

## 现状基线（Phase 1 调研，2026-07-08）

- 上游 issue #1358「3DGS Rasterizer Support」已 **closed**，由 Genesis 1.0 的 **Nyx** 路径追踪渲染器解决。
- Nyx = `gs-nyx-plugin`（PyPI），camera sensor 接口；splat 走 `LightFieldAsset(GaussianField)`。
- **更正**：Nyx README 称「需 NVIDIA CUDA」，但实测引擎是 **Vulkan 硬件光追**（非 CUDA/OptiX，输出走 DLPack）。AMD RDNA4 + Mesa 25 RADV 已验证支持 Vulkan 光追 → **AMD 路径可行**，目标节点定为 9700（`10.161.176.9`），base 镜像 `genesis-nyx-amd:latest`。
- 实验资产：worldlabs rustic kitchen splat PLY（500k / 2m）。

## 优先级 backlog

| 优先级 | 子任务 | 设计 | 实验 | 状态 |
|---|---|---|---|---|
| P0 | feature1：AMD 上跑通 Nyx，渲染 rustic kitchen splat 出图 | [feature1](features/feature1_nyx_3dgs_render.md) | [part1](exp/part1-exp.md) | 🚧 **BLOCKED** — Nyx init 硬依赖 CUDA `cuInit`，闭源不可自修；上游 [genesis-nyx #18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18) |
| P1 | feature2：splat + mesh（如 Franka/URDF 或 primitive）同帧路径追踪渲染 | - | - | 待拆 |
| P2 | feature3：多相机 / 多环境批渲染 + 渲染性能（fps/spp）压测 | - | - | 待拆 |
| P2 | feature4：SPZ 格式 / 高精度 mesh(GLB) 导入对比 | - | - | 待拆 |

## 结论速查（跨 feature，回填）

- **Nyx = Vulkan 光追，非 CUDA**：`gs_nyx` 二进制链 `libvulkan.so.1`，符号 spirv=770/raytracing/acceleration，cudart=0/optix=0；输出走 DLPack。→ AMD 有可行路径。（证据：[part1 E0](exp/part1-exp.md)）
- **RDNA4 需 Mesa ≥ 24.3**：Mesa 25 RADV 认出 `GFX1201` DISCRETE_GPU 且支持 rayTracingPipeline/accelerationStructure；旧 Mesa 23.2 只见 llvmpipe(CPU)。（证据：[part1 E1](exp/part1-exp.md)）
- **base 镜像**：`genesis-nyx-amd:latest`（rocm/pytorch 24.04 + Mesa25 + genesis1.2.1 + nyx；ROCm torch 2.10）。（[Dockerfile](../Dockerfile)）
- headless 不影响 Nyx 离屏渲染（RADV 走 /dev/dri，无需 X/Wayland）。
- **⚠️ AMD 开箱不可用（BLOCKED）**：`gs-nyx-plugin` `scene.build()` 缺 `libcuda.so` → SIGABRT；stub 后报 `cuInit` 缺失 = 真调 CUDA API（非 triton 噪声）。引擎层(Vulkan RT)兼容 RDNA4，发行版闭源被 CUDA 绑死，不可自修。已提上游 [genesis-nyx #18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18)。（证据：[part1 E3/E3.1](exp/part1-exp.md)）
