# 资产文档：ClothesNet（真实衣物网格）

状态：**导入准备中（2026-06-18）**。数据集本地下载中，本文记录"如何接入本仓库的 Genesis PBD 衣物管线"。

## 1. 数据集是什么

- ClothesNet：信息丰富的 3D 衣物模型库（ICCV 2023），约数千件、多类别（上衣/裤子/裙子/连衣裙/帽子等），
  含三角网格 + 纹理，部分带关键点/语义标注。
- 我们当前**只需要单件衣物的三角网格（.obj）**作为 feature4/5 的真实衣物资产，替换程序生成的
  tube / 平布 proxy。纹理与标注暂不使用。

> 数据集详情与下载来源见调研记录（豆包对话）：<https://www.doubao.com/chat/38431338286939650>

## 2. 本地存放约定

- 原始下载（大、不入库）：`assets_raw/clothesnet/`（加入 `.gitignore`，**不提交**）。
- 仓库内只保留**挑选并归一化后的少量 obj**：`meshes/clothesnet/<category>_<id>.obj`（小、可入库）。
- 远端 GPU 节点通过 `git pull` 拿到 `meshes/clothesnet/*.obj` 即可，原始库不上传。

> 待办：把本地下载实际路径填到这里：`本地路径 = <填写>`。

## 3. 导入 Genesis 的转换流程（关键）

现有脚本 `scripts/50_garment_pick_place.py` / `40_garment_selfcollision_grasp.py` 已支持 `--mesh <path>`，
内部用 `gs.morphs.Mesh(file=..., scale=..., pos=..., euler=...)` + `gs.materials.PBD.Cloth`。
直接喂真实 obj 前需做 **4 步归一化**（否则尺寸/朝向/粒子数会出问题）：

1. **单位与尺度**：读 bbox，把最大边缩放到 ~0.3–0.5m（人手可抓的衣物尺度）。记 `scale`。
2. **朝向**：让衣物"可悬挂"——脚本按"钉最高一圈粒子当作顶边"悬挂，需要衣物长轴沿 Z。
   多数 obj Y 向上 → 用 `euler=(90,0,0)` 把 Y 转到 Z（与现有平布一致），按实际再调。
3. **网格密度（决定 PBD 粒子数）**：PBD 把网格顶点当粒子。顶点太多（>~3k）会很慢、
   太少（<~300）抓取不稳。目标 **~500–1500 顶点**。过密则用 decimate（见下）。
4. **水密/法向**：非必须，但破面会让 self-collision 行为异常；优先选完整闭合或单层的衣物。

### 推荐预处理（一次性，本地做）

用 trimesh 归一化 + 抽稀，产出仓库内 obj：

```python
import trimesh, numpy as np
m = trimesh.load("assets_raw/clothesnet/<...>.obj", force="mesh")
m.apply_translation(-m.bounds.mean(0))                 # 居中
s = 0.4 / m.extents.max()                              # 最大边 -> 0.4m
m.apply_scale(s)
if len(m.vertices) > 1500:                             # 控制粒子数
    m = m.simplify_quadric_decimation(1200)
m.export("meshes/clothesnet/dress_0001.obj")
print(len(m.vertices), m.extents)
```

## 4. 与 feature4 / feature5 的对接

- feature5 跑真实衣物：
  ```
  python scripts/50_garment_pick_place.py --mesh meshes/clothesnet/dress_0001.obj \
      --scale 1.0 --particle-size 0.012 --ep 0 --target-x 0.75 --target-y 0.02 --render
  ```
  （已归一化的 obj 用 `--scale 1.0`；`particle_size` 据顶点间距调，先 0.012 再试。）
- **抓取/放置偏移会变**：feature5 的"落地铺展偏移"（平布约 +0.33m，见 `part5-exp.md`）对真实衣物不同，
  需对新资产重新标定 `--offset-x/--offset-y`。
- 顶边悬挂假设对**非矩形衣物**可能不自然（如连衣裙肩部）→ 可能要改钉取点策略（按特定关键点/最高 N 颗）。

## 5. 风险 / 待验证

| 风险 | 说明 | 应对 |
|------|------|------|
| 顶点数过大 | 真实衣物常 >1万顶点 → PBD 卡/爆 | 预处理 decimate 到 ~1.2k |
| 破面/非流形 | self-collision 行为异常 | 选单层完整件，或 trimesh 修复 |
| 朝向不对 | 悬挂/抓取失败 | 逐件目测调 `euler` |
| 尺度错 | 抓不到/穿插 | bbox 归一化到 ~0.4m |
| 偏移失效 | 落地铺展与平布不同 | 重标定 offset |
| 许可证 | 数据集 license 限制 | 仅本地用，不提交原始库 |

## 6. Next Step

1. 数据集下载完成后，挑 1 件代表性衣物（建议先 T 恤或方巾类，最接近已验证平布）。
2. 跑预处理脚本产出 `meshes/clothesnet/<id>.obj`（顶点 ~1k）。
3. 先 `40_*`/静置验证 finite + self-collision 稳定，再 `50_*` 抓取+放置，重标定 offset。
4. 结果写回 `part4-exp.md` / `part5-exp.md`，并把可入库 obj 提交。
