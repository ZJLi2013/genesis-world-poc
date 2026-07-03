# feature5：可重复衣物操作任务 + 成功率指标

状态：**as-built ✅（平布 6/6）**。证据见 `../exp/part5-exp.md`。

> **落地结论**：抓悬挂布 → attach+解钉 → 抬起 → 移到目标 → 低位松开。**N=6 成功率 6/6=1.00，平均落点误差 0.047m**（演示 `output/feature5/feature5_pick_place.mp4`）。三个关键发现：
> ① 资产用**平布**（自然铺展、放置温柔）远好于刚性 tube（会甩飞）；
> ② 片状布落地向 +X **自然铺展 ~0.33m**，专家用 `--offset-x` 补偿即可精准命中；
> ③ 运动用**关节空间插值 + 短行程 + 消摆 dwell** 稳定，笛卡尔逐点重解 IK 反而抖动甩布（已弃）。
> **可靠包络**：gx=0.42、target x∈[0.68,0.78]、|y|≤0.04；越界会甩飞。
> **给 feature6 的硬约束**：录制 obs 必须含衣物形态 + target 位姿，否则策略非单值。
> 真实衣物接入（Ripped Shirt）见 `../cloth_asset.md` + feature8；换资产需重标定 offset 与悬挂钉取策略。

## 目标

在 feature3/4 抓取 baseline 之上，定义**一个可重复、可量化成功率的衣物操作任务**，
作为后续合成数据（feature6 LeRobot 数据集）的**专家轨迹来源**。

## 任务定义：衣物 pick-and-place（重定位）

- 衣物（程序生成 tube 筒裙）悬挂于随场景给定的初始位置（钉顶 rim）。
- 脚本化**专家**（读 GT 粒子状态）：自标定水平抓取近端 rim → `fix_particles_to_link` attach →
  `release_particle` 解钉顶 rim → 抬起 → 水平移动夹爪到目标 (tx,ty) 上方 → 下降 →
  `release_particle` 松开抓取粒子 → 衣物落到目标。
- 每个 episode 用不同 (garment_x, target_xy) → 覆盖工作空间、产生轨迹多样性。

为可复现，episode 参数用**确定性组合**（非 RNG）：N 个 (garment_x, target) 覆盖近/远/左/右。

## Phase 0 确认（面向 feature6 的前瞻）

本实验本身（专家成功率）well-posed：专家用 GT 状态，成功率指标无歧义。
**但为 feature6 数据采集预埋的关键约束**（skill Phase 0 教训）：
- action（抓哪、放哪）依赖 **garment 当前形态 + target 位姿**这两个随机化变量。
- → 录制数据时 observation **必须**包含 garment 状态代理（粒子/点云/图像）+ target 位姿，
  否则 `π(obs)→action` 非单值，学习必败。本 feature 先把这两个变量显式化、可观测化。

## 成功判据（量化）

- `success` = 衣物质心水平距离目标 `< tol`（初定 0.10m）**且** `finite=True`。
- 辅助：`place_err`（质心到目标水平距离）、`lifted`（携带过程 zmax 是否离地，证明真抓起）。
- 指标：N episode 的 **success rate** + 平均 `place_err`。

## 实验设计

脚本：`scripts/50_garment_pick_place.py`（复用 feature4 自标定抓取 + attach + 解钉）。
- 单进程跑**一个 episode**（gs.init 仅一次/进程），参数 `--garment-x --target-x --target-y --ep`，
  打印结果行 `[f5-ep] ...`；N 个 episode 用显式串联多次调用编排（规避 shell 循环变量转义）。
- `--render` 开关：成功率扫描不渲染（快）；单独跑一个 `--render` episode 出演示视频。

## 预期

- 假设成立：success rate 高（≥ ~5/6），`place_err` 小（< tol）。
- 假设不成立：某些 target 不可达 / 抓取失败 / 放置漂移大 → 记录失败模式，缩小工作空间或调放置策略。

## 不做

- 不做学习策略（feature6+）。
- 不做折叠等更复杂任务（先把最简 pick-place 跑出稳定成功率）。
- 不接真实衣物 OBJ（脚本留 `--mesh` 口）。
