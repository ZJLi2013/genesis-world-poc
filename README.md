# Genesis World POC


demos used to verify Genesis World features on AMD GPUs

1. [cloth-sim](./cloth_sim/) — ✅ **可用**：Genesis `PBDSolver`/`PBD.Cloth` 在 AMD R9700（RDNA4，`gs.amdgpu` 后端）跑通布料仿真，镜像 `genesis-cloth-poc:working` 开箱即用。

2. [3dgs_scene](./3dgs_scene/) — 🚧 **BLOCKED（AMD 上不支持）**：3DGS 渲染由 Nyx plugin 提供，其引擎是 Vulkan 硬件光追、RDNA4 本可兼容，但**闭源发行版在 `scene.build()` 硬依赖 NVIDIA `libcuda.so`/`cuInit`，AMD 无回退直接 SIGABRT，且无源码不可自修**。已提上游 [genesis-nyx #18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18)。结论：**当前 Genesis World 的 3DGS 渲染实质仅支持 NVIDIA GPU**。

