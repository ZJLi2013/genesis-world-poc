# feature8：真实衣物网格质量预处理 → PBD 可用

状态：**as-built（2026-07-03）**。端到端验证见 `part8-exp.md` Exp 8.1。

> **落地结论**：尖刺主因是网格**不连通**（gltf 9 个独立片各自乱飞），非 quadric sliver。
> `preprocess_garment.py` 新增「保留最大连通片(`--keep-components 1`) + 焊接 + 去退化面」后，
> Ripped Shirt 进 PBD 全程无尖刺、形态像布（视频 `output/feature5/ripped_v2.mp4`）。**零新依赖**——
> 下文设计的 pyacvd 均匀重网格（`--uniform`）已实现但本轮未启用，留作更高均匀度需求的 backlog。

## 核心判断

真实衣物 gltf/obj 直接朴素抽稀后进 Genesis PBD 会炸成尖刺（part5 Exp5.2 证伪）。
根因是**网格质量**，不是物理参数。要让真实衣物可用，预处理必须产出一张
**单一连通、三角形均匀、无退化/碎片**的三角壳。本 feature 只解决这个预处理质量问题。

## Scope

**做**：
- 升级 `scripts/preprocess_garment.py`：连通性过滤 + 焊接 + 去退化 + 均匀重网格，产出 PBD 友好 obj。
- 用 Ripped Shirt 复跑 feature5，视觉 + 指标双判据确认不再尖刺。

**不做**：
- 不改 `50_garment_pick_place.py` 物理/抓取逻辑（feature5 已验证）。
- 不做 offset 落点重标定（feature5 Next，网格质量解决后再谈）。
- 不追求保留袖子/trims 等全部部件；先保证主体衣身能干净仿真。

## Problem（part5 Exp5.2 根因）

Ripped Shirt gltf-thin 实测：
- **9 个不连通片**：主体 32,804 顶点 + 两袖 ~8k + 6 个碎 trims；顶点不重合（`merge_vertices(digits=4)` 焊不上）
  → 每片在 PBD 里独立乱飞。
- **quadric 抽稀留 sliver 三角形**：边界（armhole/领/下摆/撕裂口）处长细三角 → PBD stretch 一拉成尖刺。

## Design

预处理流水线（`preprocess_garment.py`，新增 `--uniform` 默认开）：

1. **连通性过滤**：`mesh.split()` 取顶点数最大的 1 片（`--keep-components 1`，可调）。丢碎 trims/独立袖。
2. **焊接 + 去退化**：`merge_vertices()` + 去重复面/零面积面/孤立点（trimesh `process=True` / `update_faces`）。
3. **均匀重网格**（关键）：把保形抽稀换成**边长均匀**的重网格，让 PBD 粒子间距一致：
   - 首选 `pyacvd`（ACVD 聚类均匀重网格，保面壳、不闭洞），目标 ~1.2k 顶点。
   - `pyacvd` 不可用则退回：`subdivide_to_size(max_edge)` 统一上限 + quadric 收敛到目标（次优）。
4. 居中 + 最大边→0.4m（不变），不旋转（朝向交给脚本 euler）。

方案权衡（KISS）：先试「连通性过滤 + 焊接 + 去退化」是否已足够（零新依赖）；
不够再加 `pyacvd` 均匀重网格（一个小 pip 依赖，是均匀重网格的现成工具）。实验按此顺序验。

## 影响范围

- `scripts/preprocess_garment.py`（升级；产物 `meshes/ripped_shirt.obj` 重生成）。
- 可能新增依赖 `pyacvd`/`pyvista`（仅本地预处理用，远端不需要）。

## Tests（判据）

在 Ripped Shirt 上：
- **视觉（主判据）**：悬挂/抓取/落地全程**无尖刺**，形态像衣物（首尾帧 + 视频人工核对）。
- **量化**：`finite=True`；预处理后**连通片=1**、无退化面；顶点 ~800–1500；
  单步 ms 与平布同量级（feature4 ~17–19ms）。
- 对照：与 Exp5.2 朴素版同参数（particle-size 0.012, scale 1.0）跑，只改网格。

## 边界

- 若均匀重网格后主体衣身仍在极端抓取下局部尖刺 → 降 `--verts` 或调 `particle_size`，仍不行记为 PBD 对该拓扑的限制。
- 撕裂口（破洞）本身是资产特性，重网格后仍会有自由边小 flap，属正常，不算失败。
