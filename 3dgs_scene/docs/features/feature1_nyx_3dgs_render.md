# feature1 — Nyx 渲染 3DGS splat（rustic kitchen）

> Status: 设计中（进行中）。实验证据见 [part1-exp](../exp/part1-exp.md)。

## 核心判断

Genesis 1.0 通过 Nyx plugin 原生支持 3DGS 渲染：splat 以 `LightFieldAsset` 挂到 Nyx camera，与 mesh 几何在同一路径追踪帧内渲染。本 feature 先验证「splat 单独渲染出图」这条最短可行路径。

## Scope

**做：**
- 在 4090 节点安装 `gs-nyx-plugin` + genesis-world，跑通官方 bundled 例子（`05_gaussian_splat.py`）验证插件可用。
- 用 worldlabs rustic kitchen splat PLY 替换，渲染出一张 RGB 图并取回本地肉眼验收。
- 摸清关键坑：坐标系（OpenCV→Z-up 旋转）、相机摆位、spp、PLY 格式兼容性。

**不做（留 backlog）：**
- splat + mesh 同帧（feature2）。
- 多相机/多环境批渲染、性能压测（feature3）。
- SPZ 格式、HQ mesh GLB（feature4）。
- 3DGS 训练 / 自建 splat。

## Problem

要回答：Genesis 现在到底能不能直接吃一个真实场景的 3DGS 资产并渲染出照片级图像？成本/门槛如何（硬件、API、坐标系）？

## Design

参考官方 `examples/05_gaussian_splat.py`：

```python
import genesis as gs
import gs_nyx.nyx_py_renderer as npr
import gs_nyx.nyx_py_sdk as nps
from gs_nyx_plugin.nyx_camera_options import NyxCameraOptions

gs.init()
scene = gs.Scene(sim_options=gs.options.SimOptions(dt=0.01), show_viewer=False)

kitchen = nps.LightFieldAsset()
kitchen.type = nps.ELightFieldType.GaussianField
kitchen.uri  = "assets/rustic_kitchen_500k.ply"
kitchen.rotation = nps.quaternion(...)   # OpenCV→Z-up，待实验标定

cam = scene.add_sensor(NyxCameraOptions(
    res=(1920,1080), pos=..., lookat=..., fov=..., spp=64,
    render_mode=npr.ERenderMode.FastPathTracer,
    light_fields=[kitchen],
))
scene.build(n_envs=1)
scene.step()
rgb = cam.read().rgb[0].cpu().numpy()
```

- 纯 splat 场景：splat 已 pre-lit，可先不加 env map / mesh。
- 坐标系：worldlabs OpenCV（+x left,+y down,+z forward）→ Genesis Z-up。先套用官方 plant 例子的 Z 轴 90° 旋转，再按渲染结果调。
- 相机摆位靠迭代：先给场景中心一个 lookat，绕看。

## 影响范围

新增 `3dgs_scene/scripts/render_kitchen.py`；节点上 `/home/david/zhengjli_3dgs/`（env + assets + out）。不改 cloth_sim。

## Tests / 验证标准

1. bundled `05_gaussian_splat.py` 跑通、出 png（插件 sanity）。
2. rustic kitchen 500k 渲染出非空、可辨认为厨房的 RGB 图。
3. 2m PLY 同样渲染成功，画质更细。
4. 取回本地图像肉眼验收（厨房结构可辨、无明显崩坏）。

## 边界 / 风险

- PLY 的 SH/属性布局可能与 Nyx 期望不完全一致 → 可能需转换。
- 相机初始摆位可能在场景外 → 黑图/空图，需迭代。
- 48GB 显存对 2M splat 足够，但 spp/res 拉高可能 OOM。
