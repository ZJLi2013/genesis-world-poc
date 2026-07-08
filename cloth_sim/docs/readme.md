# Genesis 柔体仿真底层 & 开源复现（尤其 AMD）

> 目的：说清 **genesis-world 柔体底层怎么实现**、以及 **哪些柔体 demo 能在 AMD 上开源复现**。
> 本 POC 走 Genesis `PBD.Cloth`（XPBD / compliance），强接触才备选 `IPC(uipc)`。

---

## 0. 系统认知：柔体仿真 = 「怎么离散软体」×「怎么处理接触」两层正交问题

### 第一层：离散/表示（软体本身怎么算）

| 方法 | 思路 | 精度 | 速度 | 典型用途 |
|---|---|---|---|---|
| Mass-Spring | 质点+弹簧 | 低 | 快 | 早期布料 |
| **PBD / XPBD** | 直接投影位置约束 | 近似（compliance 调参）| **很快、稳** | 实时布料/绳/软体、机器人 sim |
| FEM | 连续介质+有限元 | 高 | 慢（解线性系统）| 高保真软体/工程 |
| MPM | 粒子+背景网格 | 高（大变形/流固）| 慢 | 切割、雪、流固耦合 |

### 第二层：接触/碰撞（多物体不穿插）

| 方法 | 思路 | 鲁棒性 | 速度 |
|---|---|---|---|
| Penalty | 穿透加弹力推回 | 会穿插、敏感 | 快 |
| Impulse / LCP | 解互补约束 | 中 | 中 |
| **IPC**（Incremental Potential Contact）| log-barrier 势垒，**数学保证无穿插** + 可微 | **最强** | 慢（全局 Newton + 直接解）|

→ **`uipc`/libuipc 是第二层的通用 GPU 框架**：把 IPC 做成统一库，内部软体用 FEM 离散，对外提供"无穿插接触"。

---

## TL;DR

1. **Genesis 柔体是多 solver**（PBD / MPM / FEM / SPH），全部用 **Taichi（现 fork 成 Quadrants）编译到 GPU**（含 `gs.amdgpu`）。
2. **接触两条路**：① PBD/Legacy 内禀近似接触（实时、便宜）；② **IPC Coupler 高保真无穿插**，底层 **libuipc（CUDA-only）**。
3. 本 POC 用 **`PBD.Cloth`**；强接触才备选 `IPC(uipc)`。
4. **开源复现**：PBD/MPM/FEM/SPH demo 能在 **AMD 跑通**；唯独 **IPC(uipc) 因 libuipc 是 CUDA-only，在 AMD 硬阻断**。

---

## 1. Genesis 柔体底层

Genesis = 「统一引擎 + Taichi/Quadrants 编到 GPU」。柔体按材料选 solver：

| Solver | 方法 | 柔体用途 | 后端 |
|---|---|---|---|
| **PBDSolver** | PBD / XPBD | **布料**、软体、绳 | Taichi → GPU（含 `gs.amdgpu`）|
| MPMSolver | Material Point Method | 可变形体/颗粒/粘性 | Taichi → GPU |
| FEMSolver | 有限元（四面体） | 弹塑性软体 | Taichi → GPU |
| SPHSolver | 光滑粒子流体 | 液体 | Taichi → GPU |

PBD 求解核心（XPBD 约束投影）：

```
1. Predict:  v* = v + Δt·f/m ,  x* = x + Δt·v*
2. Project:  Δx = -(C + α·λ_old) / (Σ w_i|∇C_i|² + α) · ∇C ,  α = compliance/Δt²
3. Update:   v = (x_new - x_old)/Δt
```

### 接触两条路（理解 Genesis 柔体的关键）

- **Legacy / PBD 内禀接触**：位置修正 + 空间哈希自碰撞，实时、便宜、近似。**本 POC 用这条**（feature4 已验证自碰撞稳定，甜点 particle_size ~0.01–0.012）。
- **IPC Coupler（高保真）**：`gs.materials.FEM.Cloth` + `IPCCouplerOptions`，底层 **libuipc**——统一 GPU IPC 框架，保证无穿插、可微，但 **CUDA-only**（`pip install pyuipc` 仅 Win/Linux + CUDA 12.8）。

### libuipc 开源但 CUDA-only（AMD 阻断点）

- 开源：[`spiriMirror/libuipc`](https://github.com/spiriMirror/libuipc)（C++20 + CUDA）。LICENSE 为 Apache-2.0，但 `pyproject.toml` classifier 写 GPLv3（冲突）→ **商用前需向作者确认**。
- **开源 ≠ 能在 AMD 跑**：轮子/源码均为 CUDA 路径 → 这是 Genesis 高保真 IPC 布料在 AMD 上的**硬阻断**（与 PAT3D 同一 `pyuipc` 阻断）。
- 血缘（一句话）：Genesis 的 IPC Coupler 集成了 Simulation-Intelligence（Minchen Li 组）的 AL-IPC，落地代码在 libuipc(CUDA)，与其论文级 CPU 参考实现（BS-Cloth）**同源但不同工件**。本 POC 不涉及。

参考：[Genesis](https://github.com/Genesis-Embodied-AI/Genesis) · [Solvers 文档](https://genesis-world.readthedocs.io/en/v0.3.12/api_reference/engine/solvers/index.html) · [IPC Coupler](https://genesis-world.readthedocs.io/en/latest/user_guide/advanced_topics/couplers/ipc_coupler.html) · [libuipc](https://github.com/spiriMirror/libuipc)

---

## 2. 本 POC = 纯 PBD，零 FEM/IPC

- 物理：`PBDSolver` + `PBD.Cloth`（XPBD / compliance，`alpha=compliance/substep_dt²`）。
- 后端：`gs.init(backend=gs.amdgpu)` + AMD R9700（RDNA4）+ ROCm 7.x。
- 全部 5 个布料脚本均用 `gs.materials.PBD.Cloth`，无任何 FEM。

> ⚠️ Genesis 语义陷阱：**高保真 IPC 布料的材料恰好叫 `gs.materials.FEM.Cloth`**（走 IPC Coupler）。所以在 Genesis 里"用 FEM" ≈ "走 IPC(uipc)"。本 POC 仅把 `IPC(uipc)` 列为强接触**备选**、未启用 → 当前纯 PBD。

---

## 3. 开源复现结论（尤其 AMD）

| Genesis 柔体 demo | 算法 | 开源? | AMD 复现? |
|---|---|---|---|
| `PBD: cloth`（`examples/tutorials/pbd_cloth.py`）| PBD/XPBD (Taichi) | ✅ Apache-2.0 | ✅ **能**（本 POC 在 R9700 跑通 feature1–5）|
| MPM / FEM / SPH 软体 | Taichi solver | ✅ | ✅ 大概率能（同 `gs.amdgpu` 路径）|
| `IPC: robot cloth teleop`（高保真无穿插）| libuipc / pyuipc | ✅ 代码开源 | ❌ **不能**：pyuipc = **CUDA 12.8 only** |

**一句话**：Genesis 柔体 = Taichi GPU solver（PBD/MPM/FEM/SPH）+ 可选 libuipc(CUDA) 的 IPC 高保真接触。**PBD/MPM/FEM 那批能在 AMD 开源复现；唯独 IPC(uipc) 因 libuipc CUDA-only 硬阻断**——这正是本 POC 把 `IPC(uipc)` 标为"强接触备选"的原因。

---

## 4. 可选后续

1. **libuipc → ROCm/HIP 移植可行性评估**：让 Genesis 高保真 IPC 布料在 AMD 跑起来的真正关键件（blocker/工作量分析）。
2. 若 PBD 自碰撞在更极端叠衣场景不足，再评估 IPC 移植的必要性。
