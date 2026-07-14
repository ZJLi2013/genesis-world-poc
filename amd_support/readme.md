# amd_support — Genesis-world / Quadrants 在 AMD GPU 的支持与性能验证

跟进上游 [genesis-world #2962](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962)。起因是带关节机器人（Franka Panda，凸分解碰撞几何）的 `scene.build()` 在 **AMD gfx942（CDNA3 / MI300X）** 上 SIGSEGV（exit 139，无 traceback），而在 **gfx950（CDNA4 / MI350）** 上正常——是 gfx942 特有的凸碰撞 narrow-phase kernel codegen（LLVM ISel）崩溃。

作者 `hughperkins` 反馈：**Genesis-world 已能在 AMD 上跑，主线是「正确性补齐 + 性能优化」**，并给了一份 support list（评论 [#4744746163](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962#issuecomment-4744746163)）。本目录把它由浅入深拆成可执行 feature，逐一验证。

backlog / 优先级 / 硬件矩阵见 [`docs/overall_todo.md`](./docs/overall_todo.md)。

## 已提上游 PR / 反馈 ✅

- **[genesis-world #2962](https://github.com/Genesis-Embodied-AI/genesis-world/issues/2962)** 根因回复：gfx942 SIGSEGV = permlane64 codegen，[quadrants #746](https://github.com/Genesis-Embodied-AI/quadrants/pull/746) 是通用修复（需合并 + 发 release + genesis 提升 quadrants pin）；RDNA 不受影响。
- **3 个 R9700(gfx1201)/MI300(gfx942) 双卡验证的 quadrants PR**：
  - [#769](https://github.com/Genesis-Embodied-AI/quadrants/pull/769) 修 wave64 cross-half shuffle 上半 lane 选择错误（correctness）。
  - [#770](https://github.com/Genesis-Embodied-AI/quadrants/pull/770) shuffle_down 加 DPP `row_shl` 快路径（perf ~1.36×）。
  - [#773](https://github.com/Genesis-Embodied-AI/quadrants/pull/773) 修 AMDGPU 近似除法致 `floor(a/b)`/modulo 出错（correctness，fixes [#749](https://github.com/Genesis-Embodied-AI/quadrants/issues/749)）。

## 可执行 feature（本 repo 单机验证）

1. **F1 硬件矩阵复现** ✅ — stock genesis-world 跑最小 Franka repro，覆盖 gfx1201(RDNA4) / gfx942(CDNA3)（gfx950 待测）。
2. **F2 源码自建 Quadrants** ✅ — `CMAKE_ARGS=-DQD_WITH_AMDGPU=ON`；gfx942 直接验收 [#746](https://github.com/Genesis-Embodied-AI/quadrants/pull/746) 修好 SIGSEGV。
3. **F3 rigid benchmark** ✅ — 发行版栈在 gfx942 上 4/7 场景崩（含 dex_hand），#746 修好全部 7/7。
4. **F4 shuffle 特化** ✅ → PR [#769](https://github.com/Genesis-Embodied-AI/quadrants/pull/769)（cross-half correctness）+ [#770](https://github.com/Genesis-Embodied-AI/quadrants/pull/770)（DPP perf）。
5. **F6 modulo bug** ✅ → PR [#773](https://github.com/Genesis-Embodied-AI/quadrants/pull/773)：根因 `fast_math` 给 `fdiv` 打 `afn` → AMDGPU 近似倒数 → `floor`/modulo 错。
6. **F8 fast-math golden 对拍 harness** ✅ — 固化 #749 打法为可复用 CPU vs AMDGPU 对拍（[`scripts/fastmath_golden.py`](./scripts/fastmath_golden.py)）；三处跑 10/10 pass、0 可见 bug（negative result，符合预判），产出 = #773 回归护栏 + CI test 基座。见 [feature8](./docs/features/feature8_fastmath_golden_harness.md)。
7. **F5 优化 dex_hand（perf）** — 降为低优先级（P4），等有 CI 护栏再做。

## 下一步 & 不做项

优先级与 roadmap 见 [`docs/overall_todo.md`](./docs/overall_todo.md)。当前主线（本 repo 决策）：**P1 func coverage（非 rigid solver 的 AMD 覆盖矩阵）→ P2 correctness 深扫 → P3 CI 防退化（已有第一个 test：`fastmath_golden.py`）→ P4 perf**。

超出单机可落地范围（仅记录）：**list#5** GPU 侧 fast generic shuffle / kernel graph conditional node（驱动/硬件层）；**CI runner** 资源待落实（list#2/#3）；**WAVE32 vs WAVE64**（list#6）已纳入 P2——事实是 RDNA4 原生 wave32、CDNA3 原生 wave64，按各 arch 原生宽度验证正确性。

## 开发方法

feature-dev-pipeline：backlog（`docs/overall_todo.md`）→ 每个 feature 设计 + as-built（`docs/features/featureN_*.md`）→ 实现 + 实验证据（`docs/exp/partN-exp.md`）。
