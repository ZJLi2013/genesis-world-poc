# out/ — 渲染输出（按实验阶段归档）

每个子目录对应 [docs/exp/part2-exp](../docs/exp/part2-exp.md) / [part3-exp](../docs/exp/part3-exp.md) / [part4-exp](../docs/exp/part4-exp.md) 里的一个阶段。**新一批回传的图放对应子目录，别再堆在根目录。**

| 子目录 | 阶段 | 内容 | 相机 |
|---|---|---|---|
| `f5_franka/` | part5 F1/F1.1 | 真 Franka(home 弯臂姿, 58 连杆 visual `.obj`)合成进 3DGS 厨房；`f1_franka*`=统一灰(F1)，`f1_franka*_color`=按 MJCF material 上色后(F1.1，白底+黑关节+腕部彩件)。`*_front`=整机正面取景。深度/尺度/朝向对 | 室内·overview / 正面 |
| `m11_cube/` | part4 M1.1 | pybind `add_mesh`+逐帧 `set_mesh_transform`：红方块与 3dgs 厨房**同框合成+双向深度遮挡**，方块右缘→居中→左侧（`m11_00`=x-0.35 / `m11_01`=x0 / `m11_02`=x+0.35） | 室内·固定 |
| `feature2_unified/` | feature2 | vk_gs 三管线（raster/rt/hybrid）+ mesh+splat 统一渲染验证（`e2_cam*`、`verify_unified_amd*`） | 固定 |
| `m0b_orbit/` | part3 M0b | Genesis 真位姿 orbit（radius-9）→ 从**室外**回看，呈悬浮"切片"假象（保留作反面对照） | 室外环绕 |
| `e2b_wrist/` | part3 E2 | 修正标定（`s=1`、地板中心）wrist 相机 → 清晰室内厨房（有 ~90° roll） | 室内·手腕 |
| `e2c_pan/` | part3 E2c | 室内环视 pan（`s=1`、房内固定点、`up=(0,1,0)`、yaw 360°）→ 上正锐利写实厨房全景 | 室内·环视 |

> 已删除的错标定糊图：`e2scale_*`(s=6 远景)、`e2wrist_*`(s=1.5 糊)、`e2b_orbit_*`(radius-2 糊)。当前正解 = 室内取景 + `s=1` 近米制 + `up=Y`。
