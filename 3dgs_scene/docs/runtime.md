# 3dgs_scene runtime — 从 docker build 到 feature5/6 复现

> **这份文档是 feature3/4/5/6 所有「怎么跑」的唯一权威来源。** feature*.md 只写「做什么/为什么」，
> 运行环境、镜像、容器、脚本命令一律收拢到这里，避免散落导致过几天无法复现。
> 节点：R9700 `10.161.176.9`（AMD Radeon AI PRO R9700，RDNA4 / gfx1201，4×GPU）。

---

## 0. 镜像

节点上有两个职责不同的镜像。feature3/4/5/6 使用 `genesis-nyx-amd:latest`。

| 镜像 | 内容 | 用途 | 容器 | Python |
|---|---|---|---|---|
| `genesis-nyx-amd:latest` | rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12 + Mesa25 RADV + genesis 1.2.1 + nyx + vk-gs pybind | feature3/4/5/6：vk-gs 3DGS 渲染 + **feature6 GPU 双吃（`gs.gpu` 物理 + vk-gs 渲染同镜像/同容器/同进程/同卡）** | `vkgs_build` | 3.12（系统 pip） |
| `genesis-amd:latest` | conda py3.10 + genesis 1.2.1 + quadrants + ROCm torch + EGL | amd_support 的 quadrants/#746/rigid-benchmark GPU 物理验证 | `zhengjli_nyx` | 3.10（conda `py_3.10`） |

- **feature6 GPU 双吃的镜像 = `genesis-nyx-amd:latest`（容器 `vkgs_build`，image id `aa3a9cb5`）**，就是 vk-gs 渲染用的同一个镜像——genesis GPU 物理（`gs.gpu`，ROCm torch/taichi）与 vk-gs（Vulkan/RADV）在**同镜像同进程**跑，Gate A/B（2026-07-13 @ GPU2）均在此镜像内验证通过。**不需要 `genesis-amd:latest`**（那个是 amd_support 的 quadrants 物理验证专用，与 feature6 无关）。
- feature5/6 的镜像是 `genesis-nyx-amd:latest`（依据 `docs/overall_todo.md:9,46` + 本仓库 [`3dgs_scene/Dockerfile`](../Dockerfile)）。vk-gs 的 `.so` 在容器内 `/work/vk_gaussian_splatting/build/vkgs.cpython-312-*.so`。
- quadrants [#746](https://github.com/Genesis-Embodied-AI/quadrants/pull/746) 修的是 gfx942/CDNA 的 permlane64 SIGSEGV；RDNA4/gfx1201 走 native permlane64，不受此问题影响（amd_support [feature2](../../amd_support/docs/features/feature2_build_quadrants.md) line 23）。

---

## 1. 镜像构建（一次性）

### 1a. base 镜像 `genesis-nyx-amd:latest`

```bash
cd 3dgs_scene
docker build -t genesis-nyx-amd:latest -f Dockerfile .
```

[`Dockerfile`](../Dockerfile) 做的事：`rocm/pytorch:rocm7.2.3_ubuntu24.04_py3.12_pytorch_release_2.10.0` +
`mesa-vulkan-drivers vulkan-tools libvulkan1 libglfw3`（Mesa25 RADV，RDNA4 硬件光追硬门槛）+
`pip install genesis-world==1.2.1 gs-nyx-plugin`（不动 ROCm torch）。

> **RDNA4 硬门槛**：Mesa ≥ 24.3 才认 `GFX1201` 并支持 rayTracingPipeline（旧 Mesa 只见 llvmpipe/CPU）。
> 校验：`docker run --rm --device=/dev/kfd --device=/dev/dri genesis-nyx-amd:latest vulkaninfo --summary`
> 期望看到 `AMD Radeon Graphics (RADV GFX1201)`。

### 1b. vk-gs pybind `.so`（feature4 交付，base 镜像里没有，需单独编）

base 镜像**不含 vk-gs**（只有 nyx）。vk-gs 的 Python 扩展从 `vk_gaussian_splatting` 源码编（分支
`feature4_pybind`，fork `ZJLi2013/vk_gaussian_splatting`，基于 `rdna4_support`）：容器内 `cmake --build`
出 `vkgs.cpython-312-*.so`，落在 `/work/vk_gaussian_splatting/build/`。硬门槛 = Vulkan SDK **1.4.341+**、
`-DUSE_DLSS=OFF` + 4 处 NGX patch（详见 [feature2](features/feature2_vksplatting_radv.md) / `docs/upstream/pr_rdna4_support.md`）。

---

## 2. 起容器

repo 挂进 `/work`（节点上 host 侧 = `/home/david/zhengjli_3dgs_amd`，含 `vk_gaussian_splatting/` +
本仓库脚本 + `assets/`）：

```bash
docker run -d --name vkgs_build \
  --device=/dev/kfd --device=/dev/dri --group-add video \
  --ipc=host --security-opt seccomp=unconfined --network=host \
  -v /home/david/zhengjli_3dgs_amd:/work -w /work \
  genesis-nyx-amd:latest sleep infinity
```

进容器跑东西：`docker exec -it vkgs_build bash`。

**前置资产（feature6 插件默认路径，缺了会报文件不存在）**——挂载盘 `/work` 下需有：

| 路径 | 内容 | 用途 |
|---|---|---|
| `/work/assets/rustic_kitchen_2m.ply` | 厨房 3DGS splat（~136MB，2M splats） | `GsplatCameraOptions.ply` 默认值 |
| `/work/assets/franka/*.obj` | 59 件 Franka visual mesh | `GsplatCameraOptions.assets` 默认值（渲 58 件） |
| `/work/vk_gaussian_splatting/build/vkgs.cpython-312-*.so` | vk-gs pybind（§1b 编） | `VKGS_BUILD` 默认目录 |
| 容器内 `xvfb`（`/usr/bin/Xvfb`） | 无头虚拟显示 | `scene.build()` 走 pyglet 需 `DISPLAY`（Dockerfile 已装） |

**这些资产不是仓库自带、也不在镜像里，需手动准备（挂载盘 `/work` = host `/home/david/zhengjli_3dgs_amd`）：**

```bash
# ① Franka visual mesh —— Genesis 自带（pip install genesis-world==1.2.1 后就在包里），复制出来即可
docker exec -it vkgs_build bash -lc '
  G=$(python -c "import genesis,os;print(os.path.dirname(genesis.__file__))")
  mkdir -p /work/assets/franka
  cp -n "$G"/assets/xml/franka_emika_panda/assets/*.obj /work/assets/franka/   # 59 件 visual .obj
  ls /work/assets/franka/*.obj | wc -l'   # 期望 59

# ② Kitchen splat PLY —— worldlabs Marble 示例资产「Rustic kitchen with natural light」的 Gaussian splat 导出
#    （非本仓库产物；从 worldlabs Marble 下载/导出 2M-splat 版，放到 /work/assets/）。
#    坐标系 worldlabs 默认 OpenCV(+x left,+y down,+z forward)，导入 Genesis(Z-up) 的旋转标定见 franka_kitchen_common.py。
#    500k(smoke) / 2m(正式) 两档：rustic_kitchen_500k.ply / rustic_kitchen_2m.ply
ls -la /work/assets/rustic_kitchen_2m.ply   # ~136MB
```

> franka MJCF `xml/franka_emika_panda/panda.xml` 由 Genesis 通过资产搜索路径自动解析（`gs.morphs.MJCF(file="xml/...")`），无需手动拷。
> 换机器复现改路径：`--ply`/`--out-dir` 走命令行；`assets`/`cam_*` 在 `GsplatCameraOptions`（`gs_gsplat_plugin.py`）默认值里改。

---

## 3. 运行约定

- **物理后端：默认 `gs.gpu`（GPU 物理 + vk-gs 渲染同卡），`gs.cpu` 为 fallback**。feature6 S1 runner
  `--backend` 默认 `gpu`：`gs.init(gpu)` 物理与 vk-gs 渲染同进程同卡（Gate B 已验证，见 §6）；脚本在 gpu 模式
  自动把 `HIP_VISIBLE_DEVICES` 钉到 `--gpu`（免手动 export、保证同卡）。`--backend cpu` 退回物理跑 CPU、只有
  vk-gs 吃 GPU（更稳、无 compute 依赖，撞卡态问题时用）。feature5 离线管线 dump 侧仍用 `gs.cpu`（零 GPU）。
- **无头需 Xvfb**：`scene.build()` 走 pyglet，无 `DISPLAY` 抛 `NoSuchDisplayException`。容器内
  `apt-get install -y xvfb`；脚本 `ensure_display()` 自动拉起 `Xvfb :99`，或直接 `xvfb-run -a python ...`。
- **GPU 选择**：默认 `--gpu 1`；跑前 `rocm-smi --showuse` 核实空闲（节点 4 卡共享）。**gpu 物理模式务必选
  compute-健康卡**（GPU1 于 2026-07-13 被 wedge，见 §6）。
- **视频编码在 host**：容器内无 ffmpeg，渲染 `--out-dir` 指到挂载盘，由 host ffmpeg 拼 mp4。
- **渲染器每帧输出多张 buffer**（base / `_main` / `_aux1` / `_depth` …），base 的 `%04d.png` 为彩色合成图；
  ffmpeg 用 `-i xxx_%04d.png` 只取 base。
- **VKGS_BUILD 环境变量**：脚本 `sys.path` 插入的 vk-gs 目录，默认 `/work/vk_gaussian_splatting/build`，
  可用 `export VKGS_BUILD=...` 覆盖。

---

## 4. feature5 复现（离线合成：Genesis dump 位姿 → vk-gs 渲染）

两步解耦，靠 per-link 位姿 JSON。脚本在仓库 `3dgs_scene/scripts/franka_kitchen/`（容器内 `/work/franka_kitchen/`）。

```bash
# ① Genesis 侧（gs.cpu 零 GPU）：dump 各 link 世界 FK 位姿 → JSON
#    home 单帧：无参；F2 多帧 motion：--demo --interp-steps 12（pick-like 关节路点线性插值）
docker exec -it vkgs_build bash -lc \
  'cd /work && PYTHONPATH=/work/franka_kitchen python /work/franka_kitchen/franka_fk_dump.py \
     --demo --interp-steps 12 --out franka_poses.json'

# ② vk-gs 侧（GPU1）：读 JSON，add_mesh 58 件 franka visual + set_mesh_color + 逐帧 set_mesh_transform → PNG 序列
docker exec -it vkgs_build bash -lc \
  'cd /work && PYTHONPATH=/work/franka_kitchen python /work/franka_kitchen/franka_render_kitchen.py \
     --poses franka_poses.json --ply assets/rustic_kitchen_2m.ply \
     --gpu 1 --out-dir out/f5_franka'

# ③ host 侧拼视频（容器内无 ffmpeg）
ffmpeg -framerate 15 -i out/f5_franka/franka_motion_%04d.png -pix_fmt yuv420p out/f5_franka/franka_motion.mp4
```

产物见 [part5-exp](exp/part5-exp.md)（F1 静态 / F1.1 上色 / F2 motion）。坐标标定（Z-up→Y-up
`R:(x,y,z)→(x,z,-y)`、`t=(0,-1.1,0.92)`、`s=1`）与配色（sRGB→linear `**2.2`）全在
`franka_kitchen_common.py`，改标定只动这一处。

---

## 5. feature6 复现（在线 sensor：`scene.step()` 内联出帧）

feature6 把离线管线升级成 Genesis 第一类相机，**genesis + vk-gs 同一进程**（同一 `vkgs_build` 容器）。
插件 = [`scripts/franka_kitchen/gs_gsplat_plugin.py`](../scripts/franka_kitchen/gs_gsplat_plugin.py)（`GsplatCameraOptions` +
`GsplatCameraSensor(BaseCameraSensor)`）；S1 demo runner = `scripts/franka_kitchen/s1_sensor_demo.py`。

**默认：GPU 双吃（`gs.gpu` 物理 + vk-gs 渲染同进程同卡，Gate B 已验证 2026-07-13 @ GPU2）。**
`--backend gpu` 为默认；脚本自动把 `HIP_VISIBLE_DEVICES` 钉到 `--gpu`。`--gpu N` 选 compute-健康卡（GPU1 已 wedge，见 §6）：

```bash
docker exec -it vkgs_build bash -lc \
  'cd /work && PYTHONPATH=/work/franka_kitchen \
   xvfb-run -a python -u franka_kitchen/s1_sensor_demo.py \
     --gpu 2 --interp-steps 12 --res 1280 720 --out-dir out/f6_sensor'
# host 拼视频
ffmpeg -framerate 15 -i out/f6_sensor/s1_%04d.png -pix_fmt yuv420p out/f6_sensor/s1_motion.mp4
```

**Fallback：CPU 物理（`--backend cpu`）** —— 物理跑 CPU、只有 vk-gs 吃 GPU，无 compute 依赖，撞卡态/环境问题时用：

```bash
docker exec -it vkgs_build bash -lc \
  'cd /work && PYTHONPATH=/work/franka_kitchen \
   xvfb-run -a python -u franka_kitchen/s1_sensor_demo.py \
     --backend cpu --gpu 2 --interp-steps 12 --res 1280 720 --out-dir out/f6_sensor'
```

> 容器内脚本副本在 `/work/franka_kitchen/`（host 挂载盘）；仓库路径是 `3dgs_scene/scripts/franka_kitchen/`。实跑以容器内
> `PYTHONPATH=/work/franka_kitchen` + `franka_kitchen/s1_sensor_demo.py` 为准。

流程：`gs.init(gpu|cpu)` → plane + franka MJCF → `scene.add_sensor(GsplatCameraOptions(...))` → `scene.build()`
（首个 sensor 建共享 `vkgs.Renderer`，加载 kitchen splat + 58 件 franka visual）→ 每帧
`set_dofs_position(demo qpos)` + `scene.step()` + `cam.read()`（惰性触发渲染，读同一 scene 里 franka 的
**实时** link 位姿）→ `.rgb` 返回 `(720,1280,3) torch.uint8`。产物与 feature5 F2 逐帧一致。详见 [part6-exp](exp/part6-exp.md)。

---

## 6. GPU 并发 / 物理后端现状

- **单卡 render + compute 并发：✅ 已验证可行（2026-07-13）**。`franka_kitchen/gate_a_concurrent.py --gpu 2` 在健康卡
  GPU2 上连跑 90s：Vulkan 渲染 7879 帧（87.5 fps）+ torch HIP 4096² matmul 10150 iters 同卡并发，
  两侧单调推进、compute 全程存活、无 `VK_ERROR_DEVICE_LOST`/wedge。详见
  [feature6.2](features/feature6.2_rdna4_render_plus_compute.md)。community 描述的 MES/CWSR 雷区
  在本机（kernel `6.17.0-35-generic` + `cwsr_enable=1`）这轮 soak 未复现。
- **⚠️ 按卡 wedge：GPU1 已坏（compute 态）**。2026-07-13 反复在 GPU1 上跑 compute 尝试把它搞进 wedge 态：
  任何镜像（genesis / 全新官方 `rocm/pytorch:7.2.4` / `rocm/vllm-dev:7.2.1`）在 **GPU1** 首次 `torch.randn().cuda`
  即静默挂死，而 **GPU2 全部正常**、GPU3 同时有人在跑 24GB compute → 不是镜像/ROCm 栈问题，是 GPU1 单卡态坏
  （内核不报错、graphics 不受影响）。**跑 GPU compute（含 `gs.gpu`、Gate B/C）请选健康卡**（`rocm-smi --showuse`
  先看空闲、能 alloc），别用 GPU1。恢复 GPU1：本机 `rocm-smi --gpureset` **不支持**（`Not supported`），只能重启 host。
- **单卡「genesis GPU 物理 + vk-gs GPU 渲染」同进程（Gate B）：✅ 已验证（2026-07-13，GPU2）**。feature6 S1
  runner 加 `--backend gpu`，`gs.init(gpu)` 物理 + vk-gs 渲染同进程同卡跑通 49 帧（rgb 在 `cuda:0`、mean~86、
  无 wedge）。命令见 §5；关键 = `HIP_VISIBLE_DEVICES=N`（genesis compute 钉 GPU N）+ vkgs `--gpu N` 同号健康卡。
  feature6 **默认走 GPU 双吃**（`gs.gpu` 物理 + vk-gs 渲染同卡）；`gs.cpu` 为 fallback（撞卡态/环境问题时用）。
- **community 雷区背景 & workaround**（本机未复现，长 soak 仍留意）：ROCm compute（HIP/KFD）与 Vulkan（RADV）
  在 gfx11xx/12xx 混跑，有一类 AMDGPU 内核/MES 固件 bug（CWSR 上下文保存）会导致 GPU wedge / `VK_ERROR_DEVICE_LOST`
  （[ROCm#5825](https://github.com/ROCm/ROCm/issues/5825) 点名 **gfx1201**；[TheRock#2655](https://github.com/ROCm/TheRock/issues/2655) MES hang）。
  workaround：`amdgpu.cwsr_enable=0` / linux-lts 内核 / dkms 补丁 / MES 固件。HIP↔Vulkan interop 本身是官方能力
  （[rocm-examples vulkan_interop](https://github.com/ROCm/rocm-examples/tree/develop/HIP-Basic/vulkan_interop)），即 feature6 S3 零拷贝路径。
- **DLPack 零拷贝**（Vulkan external mem → HIP/torch）在 AMD 未成熟，归 feature6 S3；S1/S2 用 host numpy。
