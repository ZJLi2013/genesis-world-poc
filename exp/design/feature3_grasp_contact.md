# feature3：机器人 + 夹爪抓布接触验证

状态：设计中 →（实现后转 as-built）

## 目标 / 待验证假设

核心风险项：**PBD 布料 ↔ 刚性夹爪的接触**在 Genesis 1.1.1 + RDNA4 上是否稳定可用。
1. Franka 夹爪闭合能"夹住"布料（接触处布料随夹爪运动），而非穿透或爆飞。
2. 全程 `finite=True`，无数值发散。
3. 夹取后抬起，被夹区域布料 z 随夹爪上升（抓持成功的量化判据）。

## 方案（最小可行）

- 机器人：Genesis 自带 `xml/franka_emika_panda/panda.xml`（7 臂 DOF + 2 指 DOF，末端 link `hand`）。
- 布料：真实 `meshes/cloth.obj`，**顶边钉住**呈竖直窗帘（悬挂布料比平铺更易被平行夹爪夹取，且不与地面干涉）。
- 流程（control_dofs_position + IK）：
  1. IK 到预抓取位（夹爪张开，布面在两指之间）。
  2. 闭合手指（控制 finger DOF → 小开口/给力）。
  3. IK 抬起。
  4. 读 cloth 被夹区域粒子 z 变化 + finite。

判据：
- 被夹区域 z 上升 > 阈值（抓持成立）；
- finite=True；
- 渲染帧人工核对夹爪夹住布、布随之运动。

## 关键 API（已确认）

- `franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))`
- DOF：臂 `np.arange(7)`，指 `np.arange(7,9)`；末端 `franka.get_link("hand")`。
- 控制：`set_dofs_kp/kv`、`control_dofs_position`、`inverse_kinematics(link=, pos=, quat=)`。
- 布料钉点：`cloth.fix_particles` + `get_particles_pos`。

## 不做（后置）

- 不做复杂多步折叠/铺布操作（属 feature5 数据生成）。
- 不追求高成功率抓取策略；只验证接触链路成立。
- 不接真实机器人轨迹/遥操作。
