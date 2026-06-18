# LeHome 柔体仿真 → Genesis 迁移研究

研究 LeHome 的柔体仿真实现，并评估迁移到 Genesis-World（面向 AMD GPU）的路径。

> 说明：本文为立项背景分析（迁移自 lehome 仓库）。其中部分 Genesis API/参数为调研期推断，**已被实测修正**——
> 以实验记录为准：`part1-exp.md`（环境/渲染）、`part2-exp.md`（compliance 语义、solver α=compliance/substep_dt² 缩放、
> `find_closest_particle`、`meshes/cloth.obj`）。例如：Genesis 1.1.1 用 `stretch_compliance`/`bending_compliance`(m/N、rad/N)
> 而非 `stretch_stiffness`；`PBDOptions` 用 `max_*_solver_iterations` 而非 `iterations`/`damping`；读粒子用 `get_particles_pos`。

---

# 第一部分：LeHome 实现机制（现状）

## 1. 技术栈

- Isaac Sim 5.1（PhysX 物理 + RTX 渲染）+ Isaac Lab 2.3.1（环境框架）+ LeRobot 0.4.3（训练）。
- 柔体物理由 **PhysX** 承载，LeHome 只做家居化封装。PhysX 两套柔体能力均被使用：
  - **PBD 粒子**：布料、流体、颗粒。
  - **FEM 软体**（四面体）：体积软体。

## 2. 柔体六类

`Assets/objects` 下分 6 类：`Fluids`、`Granular`、`Linear_Objects`、`Plasmas`、`Thin-Shells`（布料/衣物）、`Volumetric_Objects`。另有 `Diverse_Manipulation_Mechanisms`（action graph 功能件）。

## 3. 三种实现路径

| 路径 | 适用 | 实现 |
|------|------|------|
| 一 | 体积软体（汉堡/枕头/玩偶） | `DeformableObjectCfg` 声明 → PhysX FEM；USD `*_Def` 已烘焙四面体网格 |
| 二 | 布料 / 流体 | 自研 `GarmentObject` / `FluidObject`，PBD 粒子，YAML 配参 |
| 三 | 场景固定件（灶台/烤箱） | 复用 `1BRAPT_LeHome.usd` 内 prim + action graph 因果逻辑 |

## 4. 布料 `GarmentObject`

`source/lehome/lehome/assets/object/Garment.py`，继承 `SingleClothPrim`（PBD 粒子布料：网格顶点为粒子，弹簧约束维形）。

- **粒子系统**：`solver_position_iteration_count`、`contact_offset`/`rest_offset`、`enable_ccd`、`self_collision`、`max_velocity`。
- **粒子材质**：`friction`、`damping`、`adhesion`、`cohesion` 等。
- **布料属性**：`stretch_stiffness`(1e8)、`bend_stiffness`(100)、`shear_stiffness`(100)、`spring_damping`(10)、`particle_mass`。
- **粒子级状态读写**（数据录制/回放核心）：GPU 走 `_cloth_prim_view.get/set_world_positions`，CPU 走 USD `points` 属性。
- `reset()`：复位初始粒子 + 域随机化位姿。

## 5. 流体 `FluidObject`

`source/lehome/lehome/assets/object/fluid.py`，手搭 `PhysxParticleSystem` + `PointInstancer`。

- **体积填充**：`generate_particles_in_convex_mesh()` 用 Delaunay 凸包 + 网格采样生成初始粒子。
- **材质**：`cohesion`、`viscosity`、`surface_tension`、`adhesion`、`density`。
- **渲染**：`PhysxParticleIsosurfaceAPI` 等值面成连续水面。
- 状态读写走 `point_instancer.GetPositionsAttr().Get/Set`。

## 6. 切割 `cutMeshNode`

`source/lehome/lehome/utils/cutMeshNode.py`，OmniGraph 节点：刀面 → `trimesh.slice_plane` 切两半 → 子网格重挂 PhysX 软体/刚体 API → 原 prim 失活。补「拓扑改变」缺口。

## 7. 主循环集成

任务继承 `BaseEnv(DirectRLEnv)`。`_setup_scene()` 构造柔体，`initialize()` 缓存初始粒子，`_reset_idx()` 复位 + 随机化，`get/set_all_pose()` 录制回放。物理步进由 PhysX 托管，LeHome 只在 reset 边界注入粒子状态、观测时读出几何。

---

# 第二部分：Genesis 布料 POC 验证（单资产）

本阶段不做 LeHome 全量 USD 资产迁移，只取**单个布料资产（毛巾/衣物）**在 Genesis + AMD 上跑通，验证可行性。

目标：单资产在 AMD 后端能加载、能仿真出合理的垂坠/折叠、能被夹爪操作、粒子状态可录制回放。其余资产类别、场景、任务批量迁移不在此范围。

布料底层 LeHome 与 Genesis 同为 PBD/XPBD，AMD 原生支持 ROCm/Vulkan，单资产 POC 的不确定项集中在接触求解器选型与物性重标定。

## 8. AMD 支持

- 统一多物理引擎：Rigid / FEM / MPM / PBD / SPH / IPC(uipc) / SAP 共享同一 scene 与 state。
- 编译器 **Quadrants**（Taichi fork）编译到 CUDA / **AMD ROCm** / Metal / Vulkan / x86 / ARM64，SIMT 原语映射到 AMD wave=64。
- AMD 入口：`gs.init(backend=gs.amdgpu)`（ROCm，仿真计算）或 `gs.vulkan`（集显/Ryzen），配 `docker/Dockerfile.amdgpu`；AMD 官方 ROCm 博客有 Genesis 教程。
- 反向自动微分全后端一等公民。
- 注：消费级卡（如 gfx1103）需设 `HSA_OVERRIDE_GFX_VERSION`；`gs.gpu` 在 Linux 默认落 CUDA，AMD 须显式指定后端。

## 9. POC 涉及的求解器

POC 只用到布料一行；其余仅作能力存在性参考（说明后续不被卡死），本阶段不实现。

| LeHome 类别 | Genesis | POC 范围 |
|-------------|---------|----------|
| **布料/衣物** | `PBDSolver` + `PBD.Cloth`；强接触切 `IPC(uipc)` | **本次验证** |
| 流体 | `SPHSolver` / `PBD.Liquid` | 不实现 |
| 体积软体 | `FEMSolver` / `MPMSolver` | 不实现 |
| 颗粒 | `MPMSolver` / `PBD.Particle` | 不实现 |
| 绳/缆 | `SFSolver` | 不实现 |
| 切割 | MPM/FEM（`coupling/cut_dragon.py`） | 不实现 |
| 机器人-布料接触 | `IPC(uipc)`（`IPC_Solver/ipc_robot_cloth_teleop.py`） | 备选（PBD 不稳时） |

## 10. 布料迁移

### 10.1 物理参数对照（重标定，非直接拷数）

| LeHome | Genesis（实测修正） | 含义 |
|--------|---------|------|
| `stretch_stiffness`(1e8) | `PBD.Cloth.stretch_compliance`(m/N，默认 1e-7) | 抗拉伸（compliance=1/刚度） |
| `bend_stiffness`(100) | `PBD.Cloth.bending_compliance`(rad/N，默认 1e-5) | 抗弯曲 |
| `shear_stiffness`(100) | PBD.Cloth 内部约束近似 | 抗剪切 |
| `particle_mass` | 材质 `rho`(kg/m²) | 面密度 |

PhysX 用绝对刚度（1e8），Genesis PBD 用 **compliance（m/N，=1/刚度）**，**必须重标定**。
关键：solver 内 `alpha=compliance/substep_dt²`，轻布需 compliance≳~1e-2 才进"软区"（详见 `part2-exp.md`）。

### 10.2 API 对照（实测修正）

| 能力 | LeHome | Genesis 1.1.1 |
|------|--------|---------|
| 创建 | `GarmentObject(...)` | `scene.add_entity(gs.morphs.Mesh(...), gs.materials.PBD.Cloth(...))` |
| 固定边/挂点 | 手动控粒子 | `cloth.fix_particles(cloth.find_closest_particle((x,y,z)))` |
| 读粒子 | `get_world_positions()` | `entity.get_particles_pos()` |
| 写粒子 | `set_world_positions()` | `entity.set_particles_pos()` |
| 步进 | Isaac Lab 托管 | `scene.step()` |

### 10.3 最小示例（AMD 后端，实测可跑）

```python
import os
os.environ["PYOPENGL_PLATFORM"] = "egl"  # RDNA4 headless 渲染必须
import genesis as gs

gs.init(backend=gs.amdgpu)
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
    pbd_options=gs.options.PBDOptions(particle_size=0.01, max_stretch_solver_iterations=8),
)
scene.add_entity(gs.morphs.Plane())
cloth = scene.add_entity(
    gs.morphs.Mesh(file="meshes/cloth.obj", scale=0.4, pos=(0, 0, 0.5)),
    material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=1e-5),
)
scene.build()
for _ in range(1000):
    scene.step()
pts = cloth.get_particles_pos()
```

## 11. 两类参数辨析：物理参数标定 vs Solver 参数

| 维度 | ① 物理参数标定（资产物性） | ② Solver 参数（数值引擎） |
|------|---------------------------|---------------------------|
| 描述 | 物体是什么材质 | 用什么算法、算多细 |
| 失败表现 | 太软/太硬、太滑/太粘 | 穿透、抖动、爆炸 |
| 手段 | 重标定数值 | 选 solver + 调稳定性 |
| 影响接触鲁棒性 | 否 | **是（决定性）** |

**① 物理参数标定**：`stretch/bending_compliance`、`friction`、`rho` 等，PhysX 绝对量 → Genesis 语义对齐。调它只改"手感"，不改鲁棒性。

**② Solver 选择（决定上限）**：一般布料 `PBDSolver`；夹爪抓薄布/叠衣/强自碰撞用 `IPC(uipc)`（保证非穿透，慢）；体积软体 `FEMSolver`/`MPMSolver`。

**② Solver 参数（微调稳定性）**：`max_*_solver_iterations`（迭代）、`dt`/substeps（时间步）、`particle_size`（碰撞间距）、自碰撞开关、CCD。

接触鲁棒性属于 ②：先换 solver（PBD→IPC）再调参，与材质 stiffness 无关。

## 12. POC 工作量

单布料资产范围内：

| 项 | 说明 | 量级 |
|----|------|------|
| 单资产导出 | 毛巾 `towel.usd` → `towel.obj`（仅取网格） | 小 |
| 机器人 | SO101/Franka 转 `MJCF/URDF` | 小-中 |
| 物性重标定 | 绝对刚度 → compliance，对齐垂坠/折叠 | 中 |
| 接触选型 | 夹爪抓布 PBD→IPC 选型 + AMD 实测 | 中（不确定项） |
| 状态读写 | `get/set_particles_pos` 录制回放对接 LeRobot | 小 |

不在本阶段：全量 USD 资产迁移、场景、action graph 逻辑、其余柔体类别。

## 13. POC 路径

1. 取 `loft_wipe`（毛巾+水），`towel.usd`→`towel.obj`，机器人转 MJCF。
2. AMD 上 `gs.amdgpu` 跑通 `PBD.Cloth` + `scene.step()`，重标定对齐垂坠/折叠。
3. 接夹爪抓取；PBD 不稳则切 IPC（`ipc_robot_cloth_teleop` 范式）。
4. 打通 `get/set_particles_pos` 录制回放，对接 LeRobot。
5. 通过后批量迁移其余资产与任务。

## 14. GPU 架构选择（布料 POC）

Genesis 已在 CDNA3（MI300/MI325）、RDNA4（R9700）、RDNA3.5（W7900）上验证（ROCm 后端）。三者物理计算（Taichi/ROCm 核）都能跑，差异在**渲染路径**——布料操作需相机 RGB 观测做数据生成与闭环评估，渲染直接决定数据质量与评估偏差。

### 渲染后端差异

| 架构 | EGL 渲染器 | 类型 | 影响 |
|------|-----------|------|------|
| CDNA3（MI300/MI325） | llvmpipe | CPU 软件光栅化 | 无图形流水线，数据生成慢，评估成功率偏低 ~20pt（render-gap bias） |
| RDNA4（R9700） | radeonsi | GPU 硬件光栅化 | 数据生成快 3–4×，无 render bias |
| RDNA3.5（W7900） | radeonsi | GPU 硬件光栅化 | 同上 |

### 实测参考（厨房抓取，可对比）

| 指标 | MI300/MI325 (CDNA3) | R9700 (RDNA4) | W7900 (RDNA3.5) |
|------|:---:|:---:|:---:|
| 渲染 | CPU llvmpipe | GPU radeonsi | GPU radeonsi |
| 训练 s/step | 0.159 | 0.11 | 0.15 |
| 数据生成 100ep | 跳过(CPU 慢) | ~23 min | ~24 min |
| 评估成功率(GPU render) | ~25%(CPU) | **~48%** | ~12% |
| ROCm | 6.x (`HSA_OVERRIDE_GFX_VERSION=9.4.2`) | 7.x | 7.x |

> W7900 评估成功率显著低于 R9700（训练 loss 收敛一致），疑似 ROCm driver 版本（7.0.2 vs 7.2）或 RDNA3.5/4 渲染差异。

### 建议

- **首选 RDNA4（R9700）**：有硬件图形流水线，训练最快、评估成功率最高、无 render-gap bias。视觉驱动的布料数据生成 + 闭环评估全流程最稳。
- **RDNA3.5（W7900）可用**：渲染同为 GPU 光栅化，但实测评估偏低，需先在 POC 中确认 driver/渲染问题。
- **CDNA3（MI300/MI325）不建议**：无图形流水线，渲染回退 CPU llvmpipe，布料这类视觉任务数据生成慢且评估有系统性偏差；仅适合用现成数据集做纯训练。

结论：布料 POC 用 **RDNA4（R9700）**。

## 15. 文件与来源

LeHome 关键文件：
- `source/lehome/lehome/assets/object/Garment.py`（布料）
- `source/lehome/lehome/assets/object/fluid.py`（流体）
- `source/lehome/lehome/utils/cutMeshNode.py`（切割）
- `source/lehome/lehome/tasks/washroom/loft_wipe.py`（布料任务示例）
- `docs/object_scene_configuration.md`（配置指南）

Genesis 参考：
- Solvers：https://genesis-world.readthedocs.io/en/latest/api_reference/engine/solvers/index.html
- PBD Cloth：https://genesis-world.readthedocs.io/en/latest/api_reference/material/pbd/cloth.html
- 布料示例：https://github.com/Genesis-Embodied-AI/genesis-world/blob/main/examples/tutorials/pbd_cloth.py
- README（Quadrants / AMD / 示例）：https://github.com/Genesis-Embodied-AI/Genesis
- AMD ROCm 博客：https://rocm.blogs.amd.com/artificial-intelligence/rocm-genesis/README.html
- AMD 后端 issue #225：https://github.com/Genesis-Embodied-AI/genesis-world/issues/225
