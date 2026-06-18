# part4 实验记录：非平面衣物 + 自碰撞稳定性 + 抓取迁移

最初要解决的问题：flat-cloth 抓取 baseline（feature3）→「真衣服」之间，最大未知是
**PBD 自碰撞在 RDNA4 上是否稳定可用**（衣物自折叠必然自接触）。
设计依据 `design/feature4_garment_asset.md`。脚本 `scripts/40_garment_selfcollision_grasp.py`。

## 总览表

| Exp | 假设 | 状态 | 关键结果 | 结论 |
|-----|------|------|----------|------|
| 4.1 | 存在 particle_size 使自折叠 finite + 低穿插 + 可接受耗时 | ✅ done | 全配置 finite、step 17–19ms、penetration ≤2% | 自碰撞稳定且廉价；越细越低 |
| 4.2 | feature3 抓取流程可迁到非平面衣物（zmin_rise>0） | ✅ done | tube 整体拎起 0.34m、fold_penetration=0 | 抓取流程可直接迁移 |

## 关键背景

Genesis **PBD 自碰撞内禀**：空间哈希做粒子碰撞，碰撞半径 = `particle_size`，无独立开关
（源码 `solvers.py` 中 `# self collision` 注释正在 `particle_size` 上方）。
→ 自碰撞核心旋钮 = `particle_size`（同时决定 remesh 后粒子数）。

## Exp 4.1：自碰撞稳定性

**判据**：`finite`（硬）、`penetration_ratio`（非相邻粒子对距离 < 0.3·particle_size 的占比，
remesh 正常邻距≈particle_size，故 <0.3 即穿插）、`step_ms`。

跨三种自折叠场景测试，结论一致稳定：

| 场景 | particle_size | n | finite | penetration_ratio | step_ms |
|------|---------------|---|--------|-------------------|---------|
| 软布堆叠(球+地面) | 0.008 | 946 | ✅ | 0.0000 | 19.1 |
| 软布堆叠 | 0.012 | 451 | ✅ | 0.0022 | 18.0 |
| 软布堆叠 | 0.020 | 185 | ✅ | 0.0216 | 17.4 |
| tube 落地(环向刚) | 0.012 | 628 | ✅ | 0.0000 | 17.1 |
| 抓取折叠(Exp4.2) | 0.012 | 627 | ✅ | 0.0000 | — |

**分析**：
- 所有配置 `finite=True`、单步 17–19ms（很快），自碰撞从不导致爆飞。
- `penetration_ratio` 随 `particle_size` 增大而升（0→0.0022→0.0216），物理上合理：碰撞半径越粗
  → 越细的折叠细节越易被压穿，但即便最粗(0.02)也仅 2%。**越细越准但越慢/粒子越多**，
  实践甜点 ~0.01–0.012。

**两次构型 pivot（诚实记录）**：
1. tube 落地：圆筒**环向(hoop)刚度**撑住不塌，penetration=0 是平凡解 → 没真正压测。
2. sphere-drape：软布(bending 1e-2)整片从球面滑落成地面 puddle，未形成干净罩面（渲染只见球）。
   → 最终以**最具衣物意义、且可靠的「抓取折叠」**作为自碰撞主证据（Exp4.2，pen=0）。

## Exp 4.2：抓取迁移（feature3 → 非平面衣物）

- 程序生成竖直 tube（筒裙，627 粒子），钉顶 rim 悬挂；复用 feature3 的**自标定水平抓取**
  + `fix_particles_to_link` attach + `release_particle` 解钉 + 拎起。
- 结果：`best euler` 自标定到水平接近；attach 46 粒子、解钉 58；
  `finite=True`、`cloth_zmin_rise=0.34`（整筒被拎离 0.34m）、`fold_penetration_ratio=0.0000`。
- 视频 `output/feature4/feature4_garment_grasp.mp4`：夹爪抓 rim → 解钉 → 整筒拎起，干净无穿插。

**结论**：feature3 抓取流程（自标定 + attach + 解钉）**无需改动即可迁到非平面衣物**。

## 总结论与 Next Step

- ✅ **PBD 自碰撞在 RDNA4 上稳定、廉价、可用**：多场景 finite、17–19ms、penetration ≤2%（甜点 particle_size ~0.01–0.012）。「真衣服」最大未知已排除。
- ✅ 抓取流程可迁移到非平面衣物。
- Next（feature5）：**一个可重复的衣物操作任务**（挂上挂钩 / 对折）+ 成功率指标，作为后续数据采集的专家轨迹来源。
- Backlog：① 接真实衣物 OBJ（脚本已留 `--mesh`）；② 若需干净 sphere-drape 罩面，调高 friction/stiffness 防滑落。
