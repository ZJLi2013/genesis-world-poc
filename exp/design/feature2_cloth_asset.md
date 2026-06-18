# feature2：单布料 + compliance 物性标定

状态：设计中 →（实现后转 as-built）

## 范围决策（KISS）

backlog 原描述为「单布料资产加载」。真实 towel.usd 资产需从 HuggingFace 拉取 lehome 资产包
（大体量下载，且当前节点无 lehome 仓库）。本阶段是 POC，**先用程序生成的布料网格**完成本 feature
的真正目标——**建立 compliance 物性标定方法论 + 验证布料行为可控**。真实资产 USD→OBJ 导入
作为后续增强项（feature2.1）。

## 假设

1. `PBD.Cloth` 的 `bending_compliance` 单调控制弯曲柔软度：compliance 越大 → 越软 → 自由边下垂越多。
2. `fix_particles` 能稳定钉住固定端，不爆飞、无 NaN。
3. RDNA4 上多次不同参数运行结果稳定可复现。

## 实验设计：悬臂垂坠（cantilever drape）

- 一块 0.4m × 0.4m 网格布（36×36）水平悬空于 z=1.0。
- 钉住 x 最小的一条边（固定端），重力使自由边下垂。
- 扫描 `bending_compliance ∈ {1e-6(硬), 1e-4, 1e-2(软)}`，`stretch_compliance` 固定 1e-7。
- 侧视相机渲染 XZ 剖面。

判据（量化）：
- `sag = pin_z - free_z`（自由边下垂量）应随 bending_compliance **单调增大**。
- `finite=True`（无 NaN/爆飞）。
- 渲染帧人工核对：硬→近似平直外伸；软→明显下垂/卷曲。

实现：`scripts/20_cloth_drape.py`、`scripts/run_feature2.sh`，结果回填 `../part2-exp.md`。

## 不做

- 不接真实 USD 资产（后置）。
- 不调机器人/夹爪（feature3）。
- 不做精确实测物性对齐（只验证「参数→行为」方向正确且单调）。
