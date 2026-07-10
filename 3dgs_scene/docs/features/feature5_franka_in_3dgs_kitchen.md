# feature5 — 真实 Franka 合成进 3DGS 厨房（对标 workshop「visual mesh 换成 3dgs」）

> Status: 🔄 **实现中**。**层定位：集成层（在线，应用向）**。从 [feature4](feature4_perframe_robot_mesh.md) 的 M1.1「占位 cube → 真 Franka mesh」拆出——feature4 交付**渲染器能力**（pybind `add_mesh`/`set_mesh_transform`/逐帧 TLAS，M1.0/M1.1 ✅），本 feature 交付**真实机器人资产 + 场景摆位 + 相机**这条应用侧集成线。
> 依赖：[feature4](feature4_perframe_robot_mesh.md)（pybind 渲染器 `Renderer.add_mesh/set_mesh_transform` ✅）、[feature3](feature3_genesis_integration.md)（Genesis↔splat 标定：`R:(x,y,z)→(x,z,-y)`、`s=1`、地板中心 `t=(0,-1.1,0.92)`、`up=Y` ✅）。
> 实验证据见 [part5-exp](../exp/part5-exp.md)。

## 核心判断（对标 workshop）

[Robot_synthetic_data_generation_workshop](https://github.com/PhysicalAI-AIM/Robot_synthetic_data_generation_workshop) 用**同一 rustic_kitchen 资产**做 Franka 抓取合成数据：kitchen **visual mesh(GLB) + collision mesh** 在 Genesis 里光栅化，Franka 抓红方块，up/wrist 双相机出 100 episode。

**本 feature = 把其中的 visual mesh 换成 3DGS**——背景厨房由 vk_gs 渲 3DGS splat（更真实的光照/材质），前景 Franka（+ 抓取物）的三角 mesh 由 Genesis 出逐帧 FK 位姿、合成进同一帧。collision/物理仍在 Genesis。即：vk_gs pybind 渲染器当「相机」，吃 Genesis 的 mesh 位姿流。

## 与 feature4 的分工

| | feature4（渲染器能力） | feature5（应用集成） |
|---|---|---|
| 交付 | pybind `Renderer`：`add_mesh`/`set_mesh_transform`/逐帧 TLAS/回读 | 真 Franka 资产装配 + workshop 摆位/相机 + episode |
| 资产 | 占位红 cube（证同框+深度） | Genesis MJCF panda 多连杆 visual `.obj` |
| 坐标 | splat 系直喂 | workshop(Genesis) 摆位/相机 → splat 系映射 |
| 里程碑 | M1.0/M1.1 ✅ | F1 静态一帧 → F2 逐帧 episode → F3 sensor+视频 |

## 资产/坐标事实（已侦察）

- **Franka visual = 多个 `.obj`**（`genesis/assets/xml/franka_emika_panda/assets/linkN_*.obj`、`hand_*.obj`、`finger_*.obj`），vk_gs `loadModel` **直接可读，无需转格式**；collision 是 `.stl`（不用）。
- **home 位姿** `HOME_QPOS=[0,-0.3,0,-2.2,0,2.0,0.79,0.04,0.04]`（经典弯臂静止姿，`set_franka_home`）。
- **workshop `floor_origin` anchor**：`base=(0,0)`、`yaw=0`、`floor_z=-0.68`、scene scale `1.5`；Franka base 在 Genesis `(0,0,-0.68)`。
- **workshop overview cam（Genesis 世界系, Z-up）**：`pos=(base_x, 0.8·s, 0.65·s+fz)`、`lookat=(base_x, -0.6·s, 0.45·s+fz)`、fov65、up=+Z。
- **Genesis→splat 映射**（feature3）：`p_splat = R·p_gen + t`，`R:(x,y,z)→(x,z,-y)`，`t=(0,-1.1,0.92)`，`s=1`。向量（up、mesh 朝向）只施 R 不平移。

## 数据流 / Pipeline

两容器分工，靠一份 per-link 世界位姿 JSON 解耦。已沉淀成 `scripts/` 下三件（无 `_` 前缀 = 耐久件）：

- **`franka_kitchen_common.py`** — 纯 numpy 复用核（两侧都 import）：Genesis(Z-up)→splat(Y-up) 映射（`R:(x,y,z)→(x,z,-y)`、`t=(0,-1.1,0.92)`）、MJCF material 配色表（sRGB→linear）、`.obj`→link 映射。改标定/配色只动这一处。
- **`franka_fk_dump.py`**（Genesis 侧，`gs.cpu` 零 GPU）— load MJCF panda + set qpos + build，dump 各 link 世界位姿到 `{"frames":[{"links":{...}}]}`。无参=home 单帧；`--qpos-json traj.json`=逐 qpos 多帧（承接 F2 motion）。
- **`franka_render_kitchen.py`**（vk_gs 侧，GPU）— 读 poses JSON，`add_mesh` 各 visual `.obj` + `set_mesh_color`（按 material）+ `set_mesh_transform`（per-link splat 变换）。单帧→渲所有相机预设；多帧→固定相机逐帧出 PNG 序列。

```text
Genesis 容器 (gs.cpu/EGL 零 GPU)                    vk_gs 容器 (vkgs_build, GPU1)
  franka_fk_dump.py                                  franka_render_kitchen.py
    load MJCF panda + set qpos + build                 read frames JSON (common 映射/配色)
    for link: (pos,quat)_world = FK  ──frames JSON──▶  add_mesh + set_mesh_color + set_mesh_transform
    dump {"frames":[{"links":{...}}]}                  set_camera(splat 预设); step; save_png
```

### 复现 / 运行（把 scripts 拷进两容器）

```bash
# 1) Genesis 侧：dump home 位姿（F1）或轨迹（F2）
python franka_fk_dump.py --out /tmp/franka_poses.json
# python franka_fk_dump.py --qpos-json traj.json --out /tmp/franka_traj.json

# 2) vk_gs 侧（franka_kitchen_common.py 需与 render 同目录；vkgs 模块在 --vkgs-build）
python franka_render_kitchen.py --poses /tmp/franka_poses.json \
  --ply /work/assets/rustic_kitchen_2m.ply --assets /work/assets/franka --out-dir out
# 多帧 motion：--cam overview --out-prefix franka_motion  → out/franka_motion_0000.png ...
```

> 路径全走 argparse（`--ply/--assets/--vkgs-build/--out-dir`，默认对齐当前容器），换环境只改参数即可。

## 实现阶梯

| 阶段 | 形态 | 内容 | 状态 |
|---|---|---|---|
| **F1** | 静态一帧 | 真 Franka(home) 多连杆 visual 合成进 3DGS 厨房 + overview cam(映射到 splat)；验尺度/朝向/落地 | ✅（+F1.1 按 MJCF material 上色）|
| **F2** | 逐帧 episode | 关节轨迹逐帧 FK → `set_mesh_transform` 更新各连杆 → Franka 在厨房里动 | 待 |
| **F3** | sensor + 视频 | 经 `gs-gsplat-plugin`(feature4 M1.2) 驱动 + 红方块抓取，出对标 workshop 的 episode 视频 | 待 |

## Scope

**做：** Genesis MJCF panda 多连杆 visual `.obj` 装配；FK per-link 世界位姿 dump；workshop 摆位/overview 相机 → splat 映射；F1 静态合成一帧 → F2 逐帧 → F3 抓取 episode。
**不做（留后续/正交）：** 3DGS→collision 几何、多环境批渲、SPZ/HQ mesh 导入；渲染器内核（feature2）；pybind 渲染器能力本身（feature4）。

## Tests / 验证标准

1. **F1**：一帧 PNG——Franka(home 弯臂)站在 3DGS 厨房地板上，尺度≈真人机械臂、up 朝上、与地板/橱柜相对位置合理，各连杆不散架。
2. **F2**：一段序列——关节动，Franka 在厨房里连贯运动，无残影（TLAS 刷新）。
3. **F3**：抓取 episode 视频，Franka+方块与 3DGS 厨房同帧深度/光照一致。
4. 全程 AMD（R9700/gfx1201）、pose-gen 零 GPU（`zhengjli_nyx` CPU/EGL）、渲染只用空闲 GPU1。

## 边界 / 风险

- **per-连杆 local offset**：假设 visual `.obj` 顶点在 link-local 系（panda MJCF 惯例）；若某 link 的 geom 有非平凡 local pos/quat，会轻微错位 → F1 先看整体，必要时从 Genesis vgeom 取精确 per-geom 世界变换。
- **workshop 尺度 vs splat 尺度**：workshop 把 GLB ×1.5 至米制，splat 亦近米制（feature3 `s=1`）；两者均代表真实米制厨房，故 Franka(真实米制)直接放、cam 偏移按米制。若整体偏大/偏小，回看是否需在 base 附近微调 `t`/朝向（经验校准，非本质）。
- **连杆数量 = mesh 实例数**：Franka ~50+ 个 visual `.obj` part → 同样多 mesh 实例 + TLAS 项；先验证正确性，性能随后。
- **GPU 纪律**：渲染 `gpu=1`，跑前 `rocm-smi --showuse` 核实不碰他人 GPU0。
