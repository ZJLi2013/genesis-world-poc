# genesis-cloth-poc

在 AMD RDNA4（R9700）上用 Genesis 做布料/衣物仿真的 POC，验证具身操作场景「单资产 → 抓取 → 数据录制 → 数据生成 → 闭环评估」全链路。

背景与可行性分析见 lehome 仓库 `exp/study.md`（本 repo 不依赖 lehome 代码，仅复用其结论与资产网格）。

## 环境

- 硬件：AMD R9700（RDNA4），ROCm 7.x，radeonsi GPU 硬件光栅化。
- 物理：Genesis `PBDSolver` + `PBD.Cloth`；强接触备选 `IPC(uipc)`。
- 后端：`gs.init(backend=gs.amdgpu)`（计算）/ `gs.vulkan`（渲染），实测确认见 `exp/part1-exp.md`。

## 开发方法

feature-dev-pipeline：backlog（`exp/overall_todo.md`）→ 设计（`exp/design/`）→ 实现+实验（`exp/partN-exp.md`）→ 回填结论（本 README「结论速查」）。

## 结论速查（conclusions-log）

> 每完成一个 feature 回填一行：结论 + 关键证据 + 对后续影响 + 指回 partN。

- **[feature1 ✅] Genesis 1.1.1 布料仿真在 R9700(RDNA4) 跑通**：`gs.amdgpu` 原生生效（29.86GB），PBD 布料 step 无 NaN，EGL GPU 渲染出图。三个环境约束影响所有后续 feature：① numpy 须降到 1.26.4（镜像 torch/genesis 按 numpy-1.x 编译）；② 渲染须强制 `PYOPENGL_PLATFORM=egl`（镜像预设 glx）；③ `PBD.Cloth` 用 compliance 语义（1/刚度）。证据/复现见 `exp/part1-exp.md`。
- **[feature2 ✅] compliance 物性标定图谱建立**：`stretch_compliance` 是有效旋钮，转折点 ~1e-1…1e0（≤1e-2 不可伸长=真实布料区，≥1e2 橡皮筋）。**关键洞察**：solver 用 `alpha=compliance/substep_dt²`，轻布需 `compliance≳1e-2` 才进软区——所以小范围扫描看不出差别，且官方示例直接用默认值(1e-7)。bending 标定需强制曲率构型 + 软区参数。社区参考：`examples/tutorials/pbd_cloth.py` 用默认参数 + `find_closest_particle` 钉点 + 自带 `meshes/cloth.obj`。证据见 `exp/part2-exp.md`。
- **[feature2.1 ✅] 真实 `cloth.obj` + bending 软区确认**：桌沿悬臂（强制曲率）+ bending 推到软区后，`droop` 随 compliance 单调增大（1e-4→0.037, 1e2→0.096），转折 ~1e-2→1e0，印证 alpha 阈值。bending 有效三要素：足够网格 + 强制曲率构型 + compliance 进软区。证据见 `exp/part2-exp.md`。
- **[feature3 ✅] Franka 夹爪水平抓取悬挂布料跑通**：固定顶边成窗帘 + **自标定夹爪朝向**（瞬移读两指坐标，选接近轴+X/手指轴Y）+ 抓近端竖边（臂展内）+ 插值接近 + 低力(−4N)闭合 → 全程 `finite=True` 无爆飞，抓取区抬升 +0.17m。**决定性坑**：自标定枚举姿态时**绝不能 `scene.step()`**（手臂甩穿布会把粒子推爆，`cloth_zmax` 从 0.63 飙到 18+）；改为仅 `set_dofs_position` 更新运动学后直接读 link 坐标。接触有效性以位移/抬升判据（PBD-刚体接触不计入 `net_contact_force`）。干净演示版用 `fix_particles_to_link`(attach) + `release_particle`(解钉顶边) 把整块布拎离（`cloth_zmin_rise=0.31m`）。证据见 `exp/part3-exp.md`。
- **[feature4 ✅] 非平面衣物自碰撞稳定性 + 抓取迁移**：Genesis PBD **自碰撞内禀**（空间哈希，碰撞半径=`particle_size`，无开关）。多自折叠场景（软布堆叠/tube/抓取折叠）均 `finite=True`、单步 17–19ms、`penetration_ratio≤2%` 且随 particle_size 单调（甜点 ~0.01–0.012）→ **自碰撞稳定廉价可用**，「真衣服」最大未知排除。feature3 抓取流程（自标定+attach+解钉）**无改动迁到 tube 衣物**，整筒拎起 0.34m、`fold_penetration=0`。脚本留 `--mesh` 口可换真实衣物 OBJ。证据见 `exp/part4-exp.md`。
