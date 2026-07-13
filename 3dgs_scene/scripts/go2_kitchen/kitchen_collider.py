"""feature9 F9b — 厨房场景碰撞几何（Marble collider GLB → Genesis）。

把 World Labs Marble sample 的厨房 collider GLB 作为**静态非凸碰撞 mesh** 加进 Genesis，
与 feature8 渲染用的 splat **同源同坐标**，故物理碰撞几何天然对齐到可视 splat 地面/墙。

坐标对齐（关键）：
  - collider GLB 与 splat 同在 Marble 空间（Y-up glTF）。
  - Genesis 加载 GLB 默认做 (X,Y,Z)→(X,-Z,Y) 的 Y-up→Z-up 转换，**恰等于 feature3 的
    R⁻¹ = SPLAT_R.T**（SPLAT_R:(x,y,z)→(x,z,-y)）。故 orientation 自动对，euler=0。
  - 只需补平移：world = R⁻¹·p_splat − R⁻¹·t ⇒ morph `pos = −R⁻¹·t = (0, 0.92, 1.1)`。
  这样 collider 的地板落在 Genesis z≈0（= splat 地板中心，feature3 标定），与 go2 物理一致，
  且经 go2_kitchen_common 的正向 R/t 映射回 splat 时与可视 splat 完全重合。

非凸静态：`convexify=False`（否则 coacd 把厨房内部凸包化 → go2 站假地面；且 10 万+三角极慢）。

用法：
    # 厨房内 drop-test（验证 go2 站在 collider 地板上、不穿模）
    python kitchen_collider.py --glb /work/assets/rustic_kitchen_collider.glb --backend gpu
"""
import argparse

import numpy as np

import genesis as gs

from go2_kitchen_common import GO2_JOINT_NAMES, GO2_STAND_POSE, SPLAT_R, SPLAT_T

# feature3 逆变换的平移分量：pos = −R⁻¹·t（R⁻¹ = SPLAT_R.T）。
COLLIDER_POS = (-SPLAT_R.T @ SPLAT_T).tolist()  # ≈ (0.0, 0.92, 1.1)


def add_kitchen_collider(scene, glb_path, decimate_face_num=0):
    """把厨房 collider GLB 作为静态非凸碰撞 mesh 加进 scene，对齐到 splat。

    decimate_face_num>0 时对碰撞 mesh 抽稀到该面数（加速 broadphase）；0 = 保留原始。
    """
    decimate = decimate_face_num > 0
    return scene.add_entity(
        gs.morphs.Mesh(
            file=glb_path,
            pos=tuple(COLLIDER_POS),
            euler=(0.0, 0.0, 0.0),  # Genesis GLB Y-up→Z-up 已 = R⁻¹
            fixed=True,
            collision=True,
            visualization=False,  # 只做碰撞，可视靠 splat
            convexify=False,  # 静态非凸，保留厨房真实内壁
            decimate=decimate,
            decimate_face_num=decimate_face_num if decimate else 500,
        ),
    )


def _np(x):
    try:
        return x.detach().cpu().numpy()
    except AttributeError:
        return np.asarray(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", type=str, default="/work/assets/rustic_kitchen_collider.glb")
    ap.add_argument("--backend", type=str, default="gpu")
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--drop-xy", type=float, nargs=2, default=[0.0, 0.0])
    ap.add_argument("--drop-z", type=float, default=0.5)
    ap.add_argument("--decimate", type=int, default=0)
    args = ap.parse_args()

    gs.init(backend=getattr(gs, args.backend), precision="32", logging_level="info")

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.02, substeps=2),
        rigid_options=gs.options.RigidOptions(enable_self_collision=False),
        show_viewer=False,
    )
    collider = add_kitchen_collider(scene, args.glb, decimate_face_num=args.decimate)
    robot = scene.add_entity(
        gs.morphs.URDF(
            file="urdf/go2/urdf/go2.urdf",
            pos=(args.drop_xy[0], args.drop_xy[1], args.drop_z),
            quat=(1.0, 0.0, 0.0, 0.0),
        ),
    )
    scene.build(n_envs=0)

    # collider 在 Genesis 空间的 bbox（验证对齐：地板应 ≈ z=0，室高 ≈ 2.3）
    try:
        aabb = _np(collider.get_AABB()).reshape(-1)
        print(f"[collider AABB gen] {aabb}", flush=True)
    except Exception as e:
        print(f"[collider AABB] n/a: {e}", flush=True)

    motors = [robot.get_joint(n).dof_start for n in GO2_JOINT_NAMES]
    robot.set_dofs_kp([20.0] * 12, motors)
    robot.set_dofs_kv([0.5] * 12, motors)
    target = np.asarray(GO2_STAND_POSE, dtype=np.float32)

    zs = []
    for i in range(args.steps):
        robot.control_dofs_position(target, motors)
        scene.step()
        z = float(_np(robot.get_pos()).reshape(-1)[2])
        zs.append(z)
        if i % 40 == 0:
            print(f"step {i:4d}  base_z={z:.4f}", flush=True)

    zs = np.asarray(zs)
    print("=== F9b kitchen-collider drop-test ===", flush=True)
    print(f"backend={args.backend} drop_xy={args.drop_xy} drop_z={args.drop_z} decimate={args.decimate}")
    print(f"base_z: start={zs[0]:.4f} min={zs.min():.4f} max={zs.max():.4f} final={zs[-1]:.4f}")
    stands = (abs(zs[-1]) < 0.6) and (zs.min() > -0.3) and (zs[-1] > -0.1)
    print("VERDICT:", "STANDS_ON_COLLIDER" if stands else "CHECK (fell through / stuck / flew)", flush=True)


if __name__ == "__main__":
    main()
