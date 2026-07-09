# amd_support — Genesis-world / Quadrants 在 AMD GPU 的支持与性能验证

跟进上游 [genesis-world #2962](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962)。起因是带关节机器人（Franka Panda，凸分解碰撞几何）的 `scene.build()` 在 **AMD gfx942（CDNA3 / MI300X）** 上 SIGSEGV（exit 139，无 traceback），而在 **gfx950（CDNA4 / MI350）** 上正常——是 gfx942 特有的凸碰撞 narrow-phase kernel codegen（LLVM ISel）崩溃。

作者 `hughperkins` 反馈：**Genesis-world 已能在 AMD 上跑，主线是「正确性补齐 + 性能优化」**，并给了一份 support list（评论 [#4744746163](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962#issuecomment-4744746163)）。本目录把它由浅入深拆成可执行 feature，逐一验证。

backlog / 优先级 / 硬件矩阵见 [`docs/overall_todo.md`](./docs/overall_todo.md)。

## 可执行 feature（本 repo 单机验证）

1. **F1 硬件矩阵复现** ✅ — stock genesis-world 跑最小 Franka repro，覆盖 gfx1201(RDNA4) / gfx942(CDNA3)（gfx950 待测）。
2. **F2 源码自建 Quadrants** ✅ — `CMAKE_ARGS=-DQD_WITH_AMDGPU=ON`；gfx942 直接验收 [quadrants#746](https://github.com/Genesis-Embodied-AI/quadrants/pull/746) 修好 SIGSEGV。
3. **F3 rigid benchmark** ✅ — 发行版栈在 gfx942 上 4/7 场景崩（含 dex_hand），#746 修好全部 7/7。
4. **F4 Quadrants shuffle 特化** — `shuffle_down`/`shuffle_up` 走 AMD 专用指令（DPP/`ds_swizzle`），跟进 [quadrants#749](https://github.com/Genesis-Embodied-AI/quadrants/issues/749)。
5. **F5 优化 rigid benchmark** — 基于 F3 优化 `dex_hand`，提 PR。

**上游反馈已发布** ✅：[genesis-world #2962](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962)（复现 + 两种修法 + 功能矩阵 + RDNA 不受影响）、[quadrants #746](https://github.com/Genesis-Embodied-AI/quadrants/pull/746)（gfx942 实测验证 + 催合并）。结论：#746 是通用修复，需合并 + 发 release + genesis 提升 quadrants pin。

## 🚫 当下不做（CI / 硬件 / 长期依赖，仅记录）

以下来自 Hugh support list，但依赖常驻 CI runner、驱动/硬件层改动或属于路线观点，超出本 repo 单机验证范围，暂不落地：

- **CDNA 正确性 CI**（list#2）：为 Quadrants / genesis-world 搭 CDNA 单元测试 CI（上游现仅 RDNA CI，EC2 V520，全线 WAVE64）。→ 需常驻 CDNA runner + 维护。
- **AMD 性能基准 CI**（list#3 CI 部分）：把 benchmark 接入 CI（对标上游 `production.yml` 的 CUDA rtx6000 流水线）。→ 需 CI 基建；本 repo 只做本地基线（F3）。
- **AMD 底层/硬件改进**（list#5）：fast generic shuffle（不经 shared memory）、kernel graph conditional node。→ 驱动/硬件层，长期。
- **WAVE32 vs WAVE64**（list#6）：Hugh 观点，WAVE64 是 outlier（Metal/Intel/CUDA 均 WAVE32），统一 WAVE32 可降低 AMD 支持成本。→ 硬件路线观点，非工程任务。

## 开发方法

feature-dev-pipeline：backlog（`docs/overall_todo.md`）→ 每个 feature 设计 + as-built（`docs/features/featureN_*.md`）→ 实现 + 实验证据（`docs/exp/partN-exp.md`）。
