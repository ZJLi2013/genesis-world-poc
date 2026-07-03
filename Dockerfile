# Genesis 布料 POC —— AMD RDNA4 (ROCm) 运行环境
# ============================================================================
# 已知能跑的镜像（feature1–5 全部在其上跑通）：
#   genesis-amd:20260611  ==  genesis-cloth-poc:working   (image id 557764ed1fd7)
#   Python 3.10 / ROCm 6.4.1 / torch 2.6.0(rocm6.4.1) / genesis-world 1.1.1 / quadrants 1.0.2
#
# ⚠️ 关键坑（务必看）：
#   genesis 建场景时会 `import skimage`，而 skimage 与 numpy 有 C-ABI 绑定。
#   - 能跑的组合：numpy==1.26.4 + scikit-image==0.25.2（本文件锁定）。
#   - 直接 `pip install genesis-world`（不锁版本）在今天会拉到 numpy 2.x，
#     导致 `ValueError: numpy.dtype size changed ... Expected 96, got 88` → 建场景崩。
#     这正是节点上 `genesis-amd:latest`(558261212d47) 坏掉的原因，勿用该 tag。
#
# 复现目标 = 上述能跑镜像。此 Dockerfile 是「从头重建」配方；若基础镜像 tag 变动，
# 最稳的办法是直接复用已保留的 genesis-cloth-poc:working（见文末备份命令）。
# ============================================================================

FROM rocm/pytorch:rocm6.4.1_ubuntu22.04_py3.10_pytorch_release_2.6.0

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace/examples

# Vulkan SDK（Genesis 的 gs.vulkan 渲染后端；计算走 gs.amdgpu 不依赖它）
RUN wget -qO- https://packages.lunarg.com/lunarg-signing-key-pub.asc \
      | tee /etc/apt/trusted.gpg.d/lunarg.asc \
 && wget -qO /etc/apt/sources.list.d/lunarg-vulkan-1.4.309-jammy.list \
      https://packages.lunarg.com/vulkan/1.4.309/lunarg-vulkan-1.4.309-jammy.list \
 && apt-get update && apt-get install -y --no-install-recommends vulkan-sdk \
 && rm -rf /var/lib/apt/lists/*

# GPU 设备访问所需用户组
RUN groupadd -f render && usermod -aG render root && usermod -aG video root

# EGL 离屏渲染（无显示器出图，脚本内也会各自 setenv）
ENV PYOPENGL_PLATFORM=egl

# Genesis + 依赖。numpy/scikit-image 显式锁版本（见文件头「关键坑」），
# torch/torchvision 沿用基础镜像自带的 ROCm 构建，切勿在此重装。
RUN pip3 install --no-cache-dir \
      "numpy==1.26.4" \
      "scikit-image==0.25.2" \
      genesis-world==1.1.1 \
      quadrants==1.0.2 \
      trimesh==4.12.2 \
      libigl==2.5.1 \
      imageio==2.37.3 \
      imageio-ffmpeg==0.6.0

# ============================================================================
# 用法
# ----------------------------------------------------------------------------
# 构建：
#   docker build -t genesis-cloth-poc:rebuilt .
#
# 起持久容器（挂载本 repo 到 /work）：
#   docker run -d --name zhengjli_cloth \
#     --device=/dev/kfd --device=/dev/dri --group-add video --ipc=host \
#     -v $(pwd):/work -w /work genesis-cloth-poc:working sleep infinity
#
# 跑 feature5（示例，真实衣物 obj）：
#   docker exec -e PYOPENGL_PLATFORM=egl -w /work zhengjli_cloth \
#     python scripts/50_garment_pick_place.py --mesh meshes/ripped_shirt.obj \
#     --scale 1.0 --particle-size 0.012 --render --out output/feature5/ripped
#
# 保留 / 离线备份能跑的镜像（防被 :latest 等覆盖或误删；tar ~30–40GB，先确认磁盘）：
#   docker tag genesis-amd:20260611 genesis-cloth-poc:working    # 已做（零成本别名）
#   docker save genesis-cloth-poc:working | gzip > genesis-cloth-poc_working.tar.gz
#   # 恢复： docker load < genesis-cloth-poc_working.tar.gz
# ============================================================================
