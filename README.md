# Genesis World POC


demos used to verify Genesis World features on AMD GPUs

1. [cloth-sim](./cloth_sim/) — ⚠️ **仅低保真 PBD 能跑，具身操作路径 BLOCKED**：`PBD.Cloth`（XPBD 近似）在 AMD R9700（`gs.amdgpu`）能跑通基础布料 + 自碰撞（feature1–5），属实时玩具级。但**做机器人抓取/高保真无穿插接触所需的 IPC（`gs.materials.FEM.Cloth` + libuipc）是 CUDA-only，在 AMD 硬阻断**——所以 lehome / IsaacSim 那种「单资产→抓取→数据录制→生成→闭环评估」的柔体操作 pipeline **当前在 AMD 跑不通**。详见 [`cloth_sim/docs/readme.md`](./cloth_sim/docs/readme.md)。

2. [3dgs_scene](./3dgs_scene/) — 🚧 **BLOCKED（AMD 上不支持）**：3DGS 渲染由 Nyx plugin 提供，其引擎是 Vulkan 硬件光追、RDNA4 本可兼容，但**闭源发行版在 `scene.build()` 硬依赖 NVIDIA `libcuda.so`/`cuInit`，AMD 无回退直接 SIGABRT，且无源码不可自修**。已提上游 [genesis-nyx #18](https://github.com/Genesis-Embodied-AI/genesis-nyx/issues/18)。结论：**当前 Genesis World 的 3DGS 渲染实质仅支持 NVIDIA GPU**。

3. [amd_support](./amd_support/) — 🚧 **进行中**：跟进上游 [genesis-world #2962](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962)，把作者反馈的 AMD 支持/性能优化 support list 拆成可执行 feature（Franka `scene.build()` 硬件矩阵复现、源码自建 Quadrants 复测 gfx942 SIGSEGV、rigid benchmark 基线、Quadrants shuffle 特化等），并向底层 [Quadrants](https://github.com/Genesis-Embodied-AI/quadrants) 提交 3 个 R9700(gfx1201)/MI300(gfx942) 双卡验证过的 PR：**① 修 wave64 cross-half shuffle 上半 lane 选择错误**（correctness，[quadrants#769](https://github.com/Genesis-Embodied-AI/quadrants/pull/769)）；**② shuffle_down 加 DPP `row_shl` 快路径**（perf ~1.36×，[quadrants#770](https://github.com/Genesis-Embodied-AI/quadrants/pull/770)）；**③ 修 AMDGPU 近似除法致 `floor(a/b)`/modulo 出错**（correctness，fixes [quadrants#749](https://github.com/Genesis-Embodied-AI/quadrants/issues/749)，[quadrants#773](https://github.com/Genesis-Embodied-AI/quadrants/pull/773)）。CI/底层硬件依赖项仅记录。见 [`amd_support/readme.md`](./amd_support/readme.md)。

