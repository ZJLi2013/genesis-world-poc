# genesis-cloth-poc

在 AMD RDNA4（R9700）上用 Genesis 做布料/衣物仿真的 POC，验证具身操作场景「单资产 → 抓取 → 数据录制 → 数据生成 → 闭环评估」全链路。

背景与可行性分析见 lehome 仓库 `exp/study.md`（本 repo 不依赖 lehome 代码，仅复用其结论与资产网格）。

## Env Setup

- 硬件/后端：AMD R9700（RDNA4）+ ROCm 7.x 宿主；容器内 ROCm 6.4.1 / Python 3.10 / torch 2.6.0。
- 物理：Genesis `PBDSolver` + `PBD.Cloth`（`gs.init(backend=gs.amdgpu)` 计算，`gs.vulkan` 或 EGL 渲染）；强接触备选 `IPC(uipc)`。

### 镜像（首选：复用能跑的镜像）

- ✅ **`genesis-cloth-poc:working`（== `genesis-amd:20260611`）**：genesis-world 1.1.1 / quadrants 1.0.2 / **numpy 1.26.4 + scikit-image 0.25.2**，开箱即用、**无需降级**。
- ⚠️ **勿用 `genesis-amd:latest`**：numpy 是 2.x，genesis 建场景 `import skimage` 会 ABI 崩（`numpy.dtype size changed ... Expected 96, got 88`）。
- 从头重建见 repo 根 `Dockerfile`（关键：锁 `numpy<2` + 匹配 skimage）：`docker build -t genesis-cloth-poc:rebuilt .`

### 起容器 + 跑

```bash
docker run -d --name zhengjli_cloth --device=/dev/kfd --device=/dev/dri \
  --group-add video --ipc=host -v $(pwd):/work -w /work \
  genesis-cloth-poc:working sleep infinity

# 最小 smoke
docker exec -e PYOPENGL_PLATFORM=egl -w /work zhengjli_cloth \
  python scripts/10_cloth_smoke.py --backend amdgpu
```

> 节点连接（IP/用户/repo 路径）、镜像备份命令等敏感/本地信息见 `exp/_local_node.md`（gitignored）。
> 远端操作两个坑：SSH 命令勿用内层双引号（PowerShell 会破坏），`docker exec` 勿加 `bash -lc`（登录 shell 会挂起 ssh 会话）。

## 开发方法

feature-dev-pipeline：backlog（`docs/exp/overall_todo.md`）→ 设计+as-built 结论（`docs/features/featureN_*.md`）→ 实现+实验证据（`docs/exp/partN-exp.md`）。

各 feature 的结论速查见 `docs/exp/overall_todo.md`「已完成」小节；逐条结论 + 关键证据回填在对应 `docs/features/*.md` 的 as-built 段。
