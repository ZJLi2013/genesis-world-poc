# 织物资产发掘（Genesis PBD.Cloth × AMD RDNA4）

> 目标：为本 POC 的 `gs.morphs.Mesh + gs.materials.PBD.Cloth` 找**能直接用的衣物三角网格**。
> 硬约束：AMD GPU 上无 CLO/Marvelous/CUDA → 只认 trimesh 能读的开放网格（OBJ / PLY / glTF/GLB / STL），专有格式先转。
> 调研日期：2026-07-03。

---

## 0. 核心判据：能不能直接进 Genesis？

Genesis 布料只吃**一块三角网格几何**（`gs.morphs.Mesh` → trimesh 读取），判据只有一条：**是不是三角网格几何 + 是不是开放/可免费转的格式**，与来自哪个平台无关。

| 格式 | 能进 Genesis？ | 做法 |
|---|---|---|
| **OBJ / PLY / STL / glTF / GLB** | ✅ 直接 | `gs.morphs.Mesh(file=...)` |
| **FBX / USD(Z/A/C)** | ⚠️ 转一道 | Blender 一步转 OBJ/GLB（§4） |
| **`.zprj`/`.zpac`**（CLO 工程）| ❌ 无 CLO 读不了 | 需正版 CLO/Marvelous 打开再 Export OBJ |
| **`.zfab`**（CLO 面料）| ❌ 无几何 | 只能抄物性参数（§1 附） |

---

## 1. 本 POC 采用件：Ripped Shirt（来源 CLO-SET Connect）

选品只认一条：CLO-SET 上**只有 Garment 类目能导出 fbx/gltf**。所以在 Store 里筛 **Garment + Free + 可导出 gltf** 即可。本 POC 用这一件：

- **[Ripped Shirt](https://connect.clo-set.com/detail/bf75add734f54f80ad106f19722fcbdd)**（Marvelous Designer 官方，**Free**，短袖女 T 恤）。
- 下载：登录 → ADD TO CART → 结算（$0）→ **My Downloads** → 格式选 **gltf (thin)**（单层、trimesh 直读、顶点少）。

### 归一化产物（实测 2026-07-03）

| 阶段 | 顶点 | 面 | 尺寸 | 单位/朝向 |
|---|---|---|---|---|
| 原始 gltf(thin) | 51,812（**9 个不连通片**）| 100,950 | 50.9×53.6×27.0 | **cm**，Y-up，不含 avatar |
| 归一化 obj | **1,276** | 2,399 | 0.24×0.40×0.11 m | m，Y-up，单连通躯干壳 |

- 脚本 `scripts/preprocess_garment.py`：**保留最大连通片(`--keep-components 1`) + 焊接去退化** → 居中 → 最大边→0.4m → 抽稀 ~1.2k（不旋转）。产物 `meshes/ripped_shirt.obj`。
- ⚠️ **连通片过滤是进 PBD 的关键**：真实衣物 gltf 常是多个不连通片（衣身/袖/trims），不过滤直接进 PBD 会各自乱飞**炸成尖刺**（见 `exp/part8-exp.md`）。多部件需保留多片时调大 `--keep-components`；要更均匀粒子加 `--uniform`（需 `pip install pyacvd pyvista`）。

### 用起来（接 feature5 抓取-放置）

```bash
# 1) 归一化（本地一次性；trimesh 4.x，CPU 即可）
python scripts/preprocess_garment.py \
    --in "assets/Ripped Shirt_thin/RippedShirt_gltf_thin.gltf" \
    --out meshes/ripped_shirt.obj

# 2) 远端 AMD 节点跑（obj 已是 0.4m 真实尺度 → --scale 1.0）
python scripts/50_garment_pick_place.py --mesh meshes/ripped_shirt.obj \
    --scale 1.0 --particle-size 0.012 --offset-x 0.18 --offset-y -0.086 \
    --garment-x 0.42 --target-x 0.70 --target-y 0.0 --render --out output/feature5/ripped
```

- 朝向：obj 保持 Y-up，脚本内 `euler=(90,0,0)` 转 Z-up → 从肩/领口顶粒子悬挂，自然。
- **落点 offset 已标定（feature5 Exp5.3）**：躯干壳专属 `--offset-x 0.18 --offset-y -0.086`（平布是 0.33），place_err 0.319→0.140。⚠️ 立体壳落点方差比平布大（开环上限 ~0.14），要更稳需闭环/放宽 tol（backlog，见 `exp/part5-exp.md`）。
- 自碰撞：T 恤前后两层必自接触，`particle-size 0.012` 落在 feature4 甜点（0.01–0.012）。

> **附**：同款若带面料件 `.zfab`（如 [Gray Washed Denim](https://connect.clo-set.com/detail/8a21f6279a3e437a9e7344c10d12c67f)，无几何 ❌），其物性可喂 feature2 标定：Weight(gsm)→质点 mass、Thickness(mm)→`particle_size`、Non-Stretch→`stretch_compliance≈1e-7`。

---

## 2. 批量来源：开源衣物网格数据集（首选，直接出 OBJ）

| 数据集 | 规模 | 格式 | 许可 | 适配度 |
|---|---|---|---|---|
| **DeepFashion3D V2** | 2078 件 / 563 实物 | `model_cleaned.obj` + 2K 贴图 | 学术 | ⭐ 真实衣物、直给 OBJ，最贴 feature4/5（[GitHub](https://github.com/GAP-LAB-CUHK-SZ/deepFashion3D)）|
| **ClothesNet** | 数千件多类 | OBJ + 纹理/标注 | 学术 | 见 §2.1（ICCV 2023）|
| **GarmentCodeData v2** | 115,000 件 | 网格（XPBD drape 产出）+ 缝纫图 | 代码 **MIT** | ⭐ 本身 XPBD 出的，物性天然接近 Genesis PBD（[代码](https://github.com/maria-korosteleva/garmentcode)）|
| **CLOTH3D** | 2M+ 帧 / 8K 序列 | OBJ(rest) + 逐帧顶点 | 需注册 | 序列数据，单件可取 rest OBJ（[GitHub](https://github.com/hbertiche/CLOTH3D)）|

> GarmentCodeData 的仿真器 fork 是 NVSCL 非商用 + 依赖 CUDA Warp，但**数据本身（网格）与 pygarment(MIT) 不受此限**——我们只取网格不跑其仿真器，AMD 无阻断。
>
> **落地顺序**：`DeepFashion3D V2`（真实直给 OBJ）→ `ClothesNet`（已在准备）→ `GarmentCodeData`（要量大时）。

### 2.1 ClothesNet 接入约定

- ClothesNet（ICCV 2023）：数千件多类别（上衣/裤/裙/连衣裙/帽等）三角网格+纹理，部分带关键点/语义标注。我们**只取单件三角网格 .obj**，纹理/标注暂不用。
- **本地存放**：原始下载 `assets_raw/clothesnet/`（加 `.gitignore`，**不提交**）；仓库内只留归一化后的少量 `meshes/clothesnet/<category>_<id>.obj`（小、可入库）。远端 GPU 节点 `git pull` 拿归一化 obj 即可。
- 归一化走 §3.2 通用流程。建议先挑最接近已验证平布的件（T 恤/方巾类）跑通 `40_*` 静置（finite + self-collision 稳）再进 `50_*` 抓放，换资产必**重标定 offset 与悬挂钉取策略**。

---

## 3. 其他来源与 USD 转换

### 3.1 Blender Studio（<https://studio.blender.org/>）

- CC-BY 开放电影角色/资产，但**主体是 `.blend` 角色**（衣服与身体缝在一起），部分需订阅。
- 用法：Blender 里打开 `.blend` → 选中衣服 mesh → 单独导出 OBJ/GLB（顺便删 body、归一化）。
- 结论：**次选**——要"批量即用 OBJ"走 §2；要"单件高质量演示衣物"可来这挑。

### 3.2 归一化流程（所有来源通用，必过）

拿到几何后都要 4 步归一化，否则尺寸/朝向/粒子数会出问题（脚本 `50_*`/`40_*` 已支持 `--mesh`）：

```python
import trimesh
m = trimesh.load("garment.glb", force="mesh")   # glb/obj/ply/stl 直读；fbx/usd 先转（§3.3）
# 若含 avatar/body：先在 Blender 里删身体，只留衣服
m.apply_translation(-m.bounds.mean(0))           # 1) 居中
m.apply_scale(0.4 / m.extents.max())             # 2) 尺度：最大边 → ~0.4m（人手可抓）
if len(m.vertices) > 1500:                        # 3) 抽稀：PBD 粒子=顶点，控制 ~500–1500
    m = m.simplify_quadric_decimation(1200)
m.export("meshes/<src>/<name>.obj")
```

4. **朝向**：长轴转到 Z（多数 Y-up 资产用 `euler=(90,0,0)`），否则悬挂/抓取不对。
5. **单层/水密**：破面会让自碰撞异常，优先选完整单层件（多不连通片见 §1 的 `--keep-components`）。
6. **物性**：几何搞定后软硬仍走 feature2 的 compliance 标定（有 `.zfab` 就抄 gsm/厚度当输入）。

### 3.3 FBX/USD → OBJ（AMD 可用）

USD/FBX 本身不是 AMD 阻断点，只是 trimesh 不直读，需转一道。**首选 Blender headless**（一个工具覆盖 FBX+USD+剥 body+归一化）：

```bash
# USD → OBJ
blender --background --python-expr "import bpy; bpy.ops.wm.usd_import(filepath='g.usd'); bpy.ops.wm.obj_export(filepath='g.obj')"
# FBX → OBJ
blender --background --python-expr "import bpy; bpy.ops.import_scene.fbx(filepath='g.fbx'); bpy.ops.wm.obj_export(filepath='g.obj')"
```

> 其他：`usdz-to-glb`（纯 JS，npx，USDZ→GLB 后 trimesh 直读）；`usdcat` 只在 USD 内部转不出 OBJ。USD 资产常来自 NVIDIA Omniverse/Isaac、Apple Quick Look、SideFX。

---

## 4. 决策速查

- **批量真实衣物 OBJ** → §2 数据集（`DeepFashion3D V2` 首选）。
- **单件高质量演示衣物** → §3.1 Blender Studio（`.blend` 剥衣服）。
- **CLO-SET 上淘** → 只取 Garment + Free + 附带 glTF/OBJ/FBX；`.zfab/.zprj` 跳过（`.zfab` 物性可抄）。
- **拿到 FBX/USD** → Blender 一步转 OBJ/GLB（§3.3）。
- **任何来源** → 进 Genesis 前必过 §3.2 四步归一化。

---

## 附：原始来源（备查）

- [CLO-SET Connect](https://connect.clo-set.com/) · [授权条款](https://legal.clo-set.com/additional-connect) · [支持的格式](https://support.clo-set.com/hc/en-us/articles/45303203188121)
- [Blender Studio](https://studio.blender.org/)（角色库 CC-BY）
- 数据集见 §2 各行链接。
