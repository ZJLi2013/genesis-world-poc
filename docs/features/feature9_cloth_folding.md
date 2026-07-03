# feature9：布料折叠任务（毛巾对折 → T-shirt 折叠）

状态：**设计中（2026-07-03）**。实验记录见 `../exp/part9-exp.md`（待建）。

> 大 feature 的收口目标：在 Genesis + AMD(RDNA4) 上做出**具身仿真里最典型的布料操作 case——叠毛巾/叠衣服**，
> 建立可复现的「抓角 → 对折 → 覆盖」任务 + 折叠质量指标。填补 Genesis 社区在**任务级折叠 case** 上的空白。

## 背景调研（为什么值得做 / 参照谁）

### Genesis 社区/官方现状：只有 building block，没有折叠任务

| 资源 | 是什么 | 缺口 |
|------|--------|------|
| [`examples/tutorials/pbd_cloth.py`](https://github.com/Genesis-Embodied-AI/genesis-world/blob/main/examples/tutorials/pbd_cloth.py) | 两块布，一块落到另一块上 + `fix_particles` 钉角 | **布料堆叠**≈叠布最原始形态，但无机器人、无任务、无成功指标 |
| `examples/coupling/cloth_on_rigid.py` | 布搭刚体的耦合演示 | 非操作任务 |
| `examples/IPC_Solver/ipc_robot_cloth_teleop.py` | 机器人遥操作布料（IPC 高保真接触） | **依赖 libuipc（CUDA-only）→ AMD 跑不了**，本项目早期已确认的阻断 |
| [Issue #199](https://github.com/Genesis-Embodied-AI/Genesis/issues/199) + PR#1767/#1309 | "夹爪抓不住布/打滑" | 官方也靠 **attach**（`CouplerOptions(rigid_pbd=True)` 物理耦合 / `fix_particles_to_link`）解决——印证本项目 feature3 的发现 |

**结论**：叠衣/叠毛巾在 Genesis 上**无现成任务范式可抄**，只有 PBD 物理原语。我们做出来即为 Genesis+AMD 上
**第一个可复现的布料折叠 case**，本身是有价值的展示点。另有一条待验证情报：`CouplerOptions(rigid_pbd=True)`
提供物理刚体-布料摩擦耦合，可能替代 attach（见 Exp 9.0）。

### 学术界范式：抓角 → 对折 → 按压 + 覆盖率/对齐度指标

叠衣是布料操作的经典 benchmark，范式高度一致，直接借鉴其**动作序列 + 指标**：

| 工作 | 任务 | 借鉴点 |
|------|------|--------|
| **SoftGym**（`ClothFold`/`ClothFlatten`/`SpreadCloth`） | 平铺布对折 / 摊平 | 标准动作 = pick 两相邻角 → 拖到对边 → 放；指标 = **粒子覆盖/对齐** |
| **SpeedFolding**（IROS'22） | 双臂高效叠衣（fling → fold） | 「先摊平再折」两阶段；折叠成功以**折线对齐 + 层叠**度量 |
| **Cloth-Funnels**（ICRA'23） | 学习式规范化叠衣 | 用**归一化覆盖率**（normalized coverage）作核心指标 |

**共识指标**（本 feature 采纳）：折叠质量不看「质心落点」（feature5 的绝对落点指标在折叠里**不适用**），
而看**相对几何**——覆盖率 coverage、折后占地收缩 footprint、折线对齐 fold-line err、平整度 flatness。

## 核心判断

折叠 = **相对几何操作**（角→角、沿中线对折）+ **多步序列**（一折→再折在已折层上重抓）。
我们已有的地基（feature3 抓取+attach、feature4 自碰撞稳定、feature5 平布 pick-place 6/6）**足够拼出折叠**，
关键新增是：① 布料**平铺台面**的初始态 + **抓角**原语；② **折叠质量指标体系**（非落点）；③ 多步序列编排。
沿用 KISS + 爬可靠区间：**先毛巾（平布，确定性强）立住范式与指标，再上真实 T-shirt（难、方差大）**。

## Scope

**做**：
- 新脚本 `scripts/60_cloth_fold.py`：平铺布 → 抓角 → 对折 → 覆盖，输出折叠质量指标 + `--render` 视频。
- 折叠质量指标模块（coverage / footprint_ratio / fold_line_err / flatness）。
- 毛巾单折（主 baseline）、毛巾两折（多步）、T-shirt 折叠（真实资产）三档实验。
- 前置廉价验证：`rigid_pbd` 物理夹持在 genesis 1.1.1 / AMD 上是否可用（Exp 9.0）。

**不做**：
- 不做学习策略（专家用 GT 粒子状态；数据录制/训练留 feature6+）。
- 不做双臂（先单臂顺序抓角，够立范式；双臂并行留 backlog）。
- 不追求 SpeedFolding 式 fling 甩平（先假设初始已大致平铺；摊平留 backlog）。
- 不改 solver/预处理逻辑（复用 feature2 参数、feature8 干净网格）。

## Problem（要跨过的三个已知难点）

1. **平铺态抓角**：折叠要求布**平铺台面**，而 feature3/5 的抓取是**悬挂**构型。平铺薄布抓单层是布料操作公认难点。
   → 专家务实做法：**attach 最近角粒子到夹爪**（`fix_particles_to_link`，feature3 已证可靠），不追求物理捏取单层。
2. **落点方差（feature5.3 教训）**：立体壳开环落点 err~0.14、方差大。折叠对相对位置更敏感。
   → 毛巾（平布）落点确定性强（feature5.1 err 0.047）→ 先用毛巾；T-shirt 折叠预判需 attach 精确 + 可能闭环。
3. **多步序列自接触**：二折要在已折双层上重抓 → 自接触。feature4 已验证 PBD 自碰撞稳定（pen≤2%），风险可控。

## Design（分档实验，逐步爬升）

脚本 `scripts/60_cloth_fold.py`：单进程跑一个 fold episode，打印 `[f9] ...` 结果行，`--render` 出视频。
复用 feature4 自标定抓取 + `fix_particles_to_link` attach + `release_particle`。

### Exp 9.0 — 抓取原语选型（廉价前置）✅ 已定
- 结论：genesis **1.1.1 无 `CouplerOptions`**（仅 SAP/IPC/Legacy 耦合；IPC=libuipc CUDA-only 阻断），
  `rigid_pbd=True` 物理夹持是新版特性，本版不可用（见 `../exp/part9-exp.md` Exp 9.0）。
- **决策**：折叠抓取原语**锁定 attach**（`fix_particles_to_link` + `release_particle`，feature3/4 已证稳定）。
  SAP 耦合 / 升级 genesis 后的物理捏取留 backlog。

### Exp 9.1 — 毛巾单折（平布对折，主 baseline）
- setup：平布落台面铺平（复用 feature5 平布可靠区间，gx≈0.42）。
- 专家：抓**相邻两角**（GT 粒子，取 x 最小侧两角）→ attach → 抬起 → 平移到**对边两角上方** → 下降 → 松开 → 上层盖下层。
- 判据（见下「折叠质量指标」）：`coverage>0.8` 且 `finite` 且视觉无尖刺。
- 预期：平布确定性强 → 稳定达成，立住范式与指标。

### Exp 9.2 — 毛巾两折（四分之一折，多步序列）
- 单折后在**已折双层**上重抓（沿另一轴的两角）再折一次。
- 压测点：重抓时自接触（feature4 已验证）+ 两步误差累积。
- 判据：两折后 `footprint_ratio≈0.25`、`coverage` 仍高、finite。

### Exp 9.3 — T-shirt 折叠（真实 CLO-SET 壳，难度上界）
- 平铺 → 折两袖 → 沿中线对折（衣物折叠标准动作）。用 feature8 干净网格 `meshes/ripped_shirt.obj`。
- 预判：feature5.3 已暴露立体壳落点方差大 → 折叠更难，**大概率需 9.0 物理夹持或闭环微调 / 放宽 coverage 门槛**。
- 诚实记录，作为「真实衣物 vs 毛巾」难度对比；即便未达毛巾水平也是有价值的边界结论。

## 折叠质量指标（本 feature 核心贡献）

抛弃 feature5 的「质心落点」，改用折叠专属指标（借鉴 SoftGym/Cloth-Funnels）：

| 指标 | 定义 | 目标 |
|------|------|------|
| `coverage` | 折后上层粒子 XY 投影落在下层轮廓内的比例 | 单折 >0.8 |
| `footprint_ratio` | 折后 XY 包围盒面积 / 折前 | 单折≈0.5，两折≈0.25 |
| `fold_line_err` | 实际折线 vs 目标中线的平均偏差 | 越小越好 |
| `flatness` | 折后 z 高度（bbox_z）/ 布厚 | 越低越平（贴合） |
| `finite` + 视觉无尖刺 | 硬门槛 | 必须通过 |

`success = coverage > 阈值 且 finite 且 视觉无尖刺`。毛巾阈值 0.8；T-shirt 视 9.3 结果可放宽并记录理由。

## 影响范围

- 新增 `scripts/60_cloth_fold.py`（复用 `50_garment_pick_place.py` 的抓取/attach 原语，抽公共函数）。
- 新增折叠指标计算（可先内联脚本，稳定后再抽模块）。
- 复用资产：平布 `meshes/cloth.obj`（毛巾）、`meshes/ripped_shirt.obj`（T-shirt，feature8 产物）。
- 实验记录 `docs/exp/part9-exp.md`；backlog `docs/exp/overall_todo.md` 加 feature9 行。

## Tests（判据）

- 9.1 毛巾单折：`coverage>0.8`、`footprint_ratio∈[0.45,0.6]`、`finite`、视觉无尖刺、首尾帧人工核对。
- 9.2 毛巾两折：`footprint_ratio≈0.25`、`coverage` 不塌、finite。
- 9.3 T-shirt：记录 coverage/footprint 实际值 + 视觉；与毛巾对比得难度结论（不设硬性通过线，重在诚实边界）。
- 全程单步 ms 与 feature4 同量级（~17–19ms/step）。

## 边界

- 平铺薄布物理抓单层不追求（用 attach 角粒子）；若未来要真实捏取，转 9.0 的 rigid_pbd 路线。
- 若 T-shirt 折叠开环方差过大（coverage 长期 <0.5）→ 记为「真实立体衣壳开环折叠的能力边界」，闭环/双臂列 backlog，不在本 feature 死磕。
- 摊平（fling/初始高度褶皱）不在 scope；假设初始大致平铺。
