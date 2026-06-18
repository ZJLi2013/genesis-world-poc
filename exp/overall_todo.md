# 布料场景仿真（Genesis × RDNA4）开发 Backlog

大 feature：在 AMD RDNA4 上用 Genesis 做布料/衣物仿真，迭代验证「单资产 → 抓取 → 数据录制 → 数据生成 → 闭环评估」全链路。
方法论：feature-dev-pipeline（Plan → Design → Build+Experiment → Close 循环）。
可行性分析依据：lehome 仓库 `exp/study.md` 第二部分。

## 现状基线

- 目标节点：AMD R9700（RDNA4），ROCm 7.x，radeonsi GPU 硬件光栅化。
- 物理：Genesis `PBDSolver` + `PBD.Cloth`（布料底层 PBD/XPBD，与 LeHome 同源）。
- 后端入口：`gs.init(backend=gs.amdgpu)`（计算）/ `gs.vulkan`（渲染），待实测确认。
- 代码现状：feature1 已落地并验证（env + PBD 布料 smoke + EGL 渲染）。
- 容器：节点已建持久容器（numpy 已降级、依赖修复完成），后续 feature 直接 `docker exec` 复用。节点/容器具体信息见本地 `exp/_local_node.md`（gitignored）。

## 优先级 Backlog

| 优先级 | Feature | 子任务 | 设计 | 实验 | 状态 |
|--------|---------|--------|------|------|------|
| **P0** | feature1 | 环境就绪 + 最小布料 smoke | `design/feature1_env_smoke.md` | `part1-exp.md` | **✅ 完成** |
| **P0** | feature2 | 布料 + compliance 物性标定 | `design/feature2_cloth_asset.md` | `part2-exp.md` | **✅ 完成** |
| **P1** | feature3 | 机器人 + 夹爪抓布接触验证 | `design/feature3_grasp_contact.md` | `part3-exp.md` | 待开始 |
| **P1** | feature4 | 粒子状态录制/回放对接 LeRobot | `design/feature4_state_io.md` | `part4-exp.md` | 待开始 |
| **P2** | feature5 | 布料数据生成流水线 | `design/feature5_datagen.md` | `part5-exp.md` | 待开始 |
| **P2** | feature6 | 闭环评估 | `design/feature6_eval.md` | `part6-exp.md` | 待开始 |

排序理由：
- P0 先解决「能不能在 RDNA4 上稳定跑出一块行为合理的布」——后续一切的地基，风险最高、杠杆最大。
- P1 解决「机器人能不能操作布 + 状态能不能进数据集」——具身操作核心闭环；接触稳定性是最大不确定项。
- P2 把单点能力扩成数据/评估流水线，依赖 P0/P1 成立。

## 已完成

- **feature1（2026-06-18）**：R9700 上 Genesis 1.1.1 布料 smoke 跑通，`gs.amdgpu` 原生 + EGL GPU 渲染。结论见 README 结论速查 / `part1-exp.md`。
- **feature2（2026-06-18）**：compliance 物性标定图谱建立（stretch 工作区间 ~1e-1…1e0；solver α=compliance/substep_dt² 缩放洞察）；对齐官方默认参数与 `find_closest_particle` / `meshes/cloth.obj` 用法。结论见 `part2-exp.md`。后置 feature2.1：真实 mesh + bending 软区标定。
