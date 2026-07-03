# feature1–4：地基阶段（环境 → 布料标定 → 抓取 → 自碰撞）

状态：**as-built ✅（2026-06-18，R9700/RDNA4 验证通过）**。合并实验记录见 `../exp/part1-4-exp.md`。

主线：在 AMD RDNA4 上把 Genesis PBD 布料从「能跑」推到「真衣服前的最大未知（自碰撞）已排除」，为后续操作任务/数据生成打地基。每个子任务当时都是独立 design 文档，因结论已收敛、exp 已合并为 `part1-4-exp.md`，这里合并留档。

---

## feature1：环境就绪 + 最小布料 smoke（P0 ✅）

**目标**：确认 RDNA4（R9700）上 Genesis 能选对后端、建 `PBD.Cloth` 场景、`step` 不崩、GPU 渲染出非空图。这是一切的地基，不引入资产/机器人。

**做法**
- `scripts/00_env_check.py`：初始化 Genesis，打印实际生效 backend / GPU / ROCm 信息。
- `scripts/10_cloth_smoke.py`：程序生成 N×N 平面布 OBJ（不依赖外部资产）+ `gs.morphs.Plane()` 地面，重力下落，挂离屏相机每隔若干步存 PNG。
- 后端默认 `gs.amdgpu`，命令行可切 `gs.vulkan` / `gs.cpu` 回退。

**验收**：backend 非回退 CPU；连续 step 1000 次无 NaN；输出 PNG 非全黑且布料形态合理。

**不确定项/回退**：`gs.amdgpu` vs `gs.vulkan` 计算/渲染归属需实测；gfx 报 "invalid device function" 时设 `HSA_OVERRIDE_GFX_VERSION`（如 `11.0.0`）；API 漂移记录到 exp 后修正脚本。

**结论**：`gs.amdgpu` 原生生效，PBD step 稳定无 NaN，EGL GPU 离屏渲染出图。

---

## feature2：单布料 + compliance 物性标定（P0 ✅）

**目标（KISS 范围）**：backlog 原为「单布料资产加载」，但真实 towel.usd 需大体量下载。本阶段先用**程序生成布料**完成真正目标——**建立 compliance 物性标定方法论 + 验证布料行为可控**；真实 USD→OBJ 导入后置（见 `cloth_asset.md`）。

**实验设计（悬臂垂坠）**：0.4×0.4m 网格布（36×36）水平悬空，钉住 x 最小边，重力使自由边下垂。扫 `bending_compliance ∈ {1e-6, 1e-4, 1e-2}`，`stretch_compliance` 固定 1e-7，侧视相机渲 XZ 剖面。

**判据**：`sag=pin_z-free_z` 随 bending_compliance 单调增大；`finite=True`；硬→近似平直外伸、软→明显下垂。

**结论**：标定方法论 + stretch 工作区间已建立。关键洞察：solver 的 `alpha=compliance/substep_dt²` 缩放（轻布需 compliance≳1e-2 才进软区）。最终实现 `scripts/22_real_cloth_bending.py`（早期悬臂/圆柱探索脚本已移除）。

---

## feature3：机器人 + 夹爪抓布接触验证（P1 ✅）

**目标**：核心风险项——**PBD 布料 ↔ 刚性夹爪的接触**在 Genesis 1.1.1 + RDNA4 上是否稳定可用。夹爪闭合能夹住布（不穿透/不爆飞）、全程 finite、抓取后被夹区 z 随夹爪上升。

**方案（最小可行）**
- 机器人：Genesis 自带 `xml/franka_emika_panda/panda.xml`（臂 7 DOF + 指 2 DOF，末端 link `hand`）。
- 布料：`meshes/cloth.obj`，**顶边钉住**呈竖直窗帘（悬挂比平铺更易被平行夹爪夹取，不与地面干涉）。
- 流程：IK 到预抓取位 → 闭合手指（finger DOF）→ IK 抬起 → 读被夹区粒子 z + finite。

**关键 API**：`add_entity(gs.morphs.MJCF(...))`；臂 `np.arange(7)`、指 `np.arange(7,9)`；`get_link("hand")`；`set_dofs_kp/kv`、`control_dofs_position`、`inverse_kinematics(link=,pos=,quat=)`；`cloth.fix_particles` + `get_particles_pos`。

**结论**：Franka 水平抓取悬挂布跑通（自标定朝向 + 低力闭合，抬升 +0.17m）。干净演示版用 `fix_particles_to_link` attach + 解钉拎离 `cloth_zmin_rise=0.308`。**关键坑：自标定枚举姿态时不能 `scene.step()`**。

---

## feature4：真实衣物资产 + 自碰撞稳定性 + 抓取迁移（P1 ✅）

**目标**：把 flat-cloth 抓取推广到**非平面衣物形状**，打掉迁向「真衣服」的最大未知——**PBD 自碰撞在 RDNA4 上是否稳定**（衣物自折叠必自接触）。

**关键背景（源码侦察）**：PBD 自碰撞是内禀的——`PBDSolver` 用空间哈希做粒子-粒子碰撞，**`particle_size` 即自碰撞半径**，`hash_grid_cell_size = 1.25 * particle_size`，无独立开关。→ 核心旋钮 = `particle_size` + 网格密度。

**资产决策（KISS）**：稳定直链 OBJ 难找 + 容器联网不确定 → 脚本内程序生成**开口圆筒（tube）**作最简 3D 衣物（前后两层壁，抓提/压扁必自接触，零下载、可复现）；脚本同时留 `--mesh <path>` 口后续无缝换真实衣物。

**实验设计**（`scripts/40_garment_selfcollision_grasp.py`）
- Exp4.1 垂坠+自碰撞：tube 竖直悬挂（钉顶 rim）自然垂坠，再制造自折叠让前后壁接触；扫 `particle_size ∈ {0.008, 0.012, 0.02}`。判据：`finite=True`（硬性）、`penetration_ratio`（非相邻粒子距离<0.5·particle_size 的比例）低、`step_ms` 可接受。
- Exp4.2 抓取迁移：把 feature3 的自标定抓取 + attach + 解钉直接迁到 tube，抓 rim 提起。判据：finite、`cloth_zmin_rise>0`、流程不挂。

**结论**：非平面衣物自碰撞稳定（多场景 finite、17–19ms、pen≤2%，甜点 `particle_size ~0.01–0.012`）；抓取流程无改动迁到 tube（整筒拎起 0.34m，`fold_penetration=0.0000`）。**「真衣服」最大未知（自碰撞）已排除**，为 feature5 操作任务铺路。

---

## 后续

真实衣物网格接入（连通片过滤/焊接/重网格）在 feature8，衣物 pick-and-place 任务在 feature5，资产发掘见 `../cloth_asset.md`。
