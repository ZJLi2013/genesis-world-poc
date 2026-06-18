# part1 实验记录：环境就绪 + 最小布料 smoke

| Exp | 目标 | 状态 | 结论 |
|-----|------|------|------|
| 1.1 | R9700 上确认 backend | ✅ 通过 | `gs.amdgpu` 原生生效，29.86 GB |
| 1.2 | cloth smoke step + 渲染 | ✅ 通过 | PBD 布料落地稳定、EGL GPU 渲染出图 |

## 环境（可复现）

- 节点：AMD R9700（RDNA4，gfx1201），ROCm 7.2。（具体 IP/hostname/用户/容器名见本地 `exp/_local_node.md`，不入 public repo）
- 镜像：`genesis-amd:latest`（Genesis **1.1.1** + quadrants + torch，已预装）。
- 持久容器：`docker run -d --name <CONTAINER> --device=/dev/kfd --device=/dev/dri --group-add video --ipc=host -v <repo>:/work -w /work genesis-amd:latest sleep infinity`
- 依赖修复（**镜像 numpy 2.2.6 与 torch/genesis/skimage 的 numpy-1.x ABI 冲突**）：
  `pip install --force-reinstall numpy==1.26.4 scikit-image==0.22.0`
- 运行：`docker exec <CONTAINER> bash -lc 'bash scripts/run_feature1.sh amdgpu'`

## 关键结果

- Exp 1.1：`Running on [AMD Radeon AI PRO R9700] with backend gs.amdgpu. Device memory: 29.86 GB`，env_check exit=0。
- Exp 1.2：`cloth particles shape=(2038, 3) finite=True z_min=0.0050 z_max=0.0050`，smoke exit=0。布料下落后完全铺平静止于地面，无 NaN。渲染帧 `output/feature1/smoke/frame_*.png`（640×480，~50KB，棋盘地面 + 白色布片，GPU 渲染正常）。

## 踩坑与修复（影响后续 feature）

1. **API 漂移**：Genesis 1.1.1 ≠ 文档 0.4.x。
   - `PBDOptions`：用 `max_stretch_solver_iterations` / `particle_size`，无 `iterations`/`damping`。
   - `PBD.Cloth`：**compliance 语义** —— `stretch_compliance`(默认 1e-7)、`bending_compliance`(1e-5)，compliance = 1/刚度，越小越硬；无 `stretch_stiffness`/`thickness`。
2. **numpy ABI**：镜像装 numpy 2.2.6，但 torch/genesis/skimage 按 numpy-1.x 编译 → `torch.from_numpy` 报 "Numpy is not available" + skimage dtype 错。降到 `numpy==1.26.4` + `scikit-image==0.22.0` 解决。（注意：与 workshop 镜像相反，那个镜像 torch 按 numpy2 编译。）
3. **headless 渲染**：镜像把 `PYOPENGL_PLATFORM` 预设为 `glx`（无显示会崩）。必须在 import genesis 前【强制】`os.environ["PYOPENGL_PLATFORM"]="egl"`（不能用 setdefault/`:-`，否则保留镜像的 glx）。EGL → radeonsi GPU 离屏渲染。
4. **SSH 操作**：PowerShell 不支持 `&&`；内联 python/grep 的嵌套引号与 `|` 易被 PowerShell 误解析；链式多命令 + 长跑易挂起 → 远端用**单条命令**最稳。

## Next Step

feature1 关闭，结论回填 README 结论速查。下一步 feature2：单布料资产 + 物性（compliance）标定，验证垂坠/折叠行为。
