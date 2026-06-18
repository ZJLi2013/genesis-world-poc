"""feature5: 衣物 pick-and-place 专家任务(单 episode/进程) + 成功判据。

衣物用平布(meshes/cloth.obj, 沿用 feature3 已验证的抓取), 比 tube 更像衣物、放置更温柔。
复用 feature3 自标定水平抓取 + fix_particles_to_link(attach) + release_particle(解钉)。
流程: 钉顶边悬挂 → 抓近端竖边 → attach → 解钉 → 适度抬起 → 移到目标上方(消摆) →
       下降到低位(消摆) → 松开 → 布落到目标。
success = 衣物质心到目标水平距离 < tol 且 lifted 且 finite。

用法(单 episode):
    python scripts/50_garment_pick_place.py --ep 0 --garment-x 0.42 --target-x 0.45 --target-y 0.10 \
        --out output/feature5/ep0 [--render]
N 个 episode 用显式串联多次调用编排, 再 grep [f5-ep] 统计 success rate。
"""
import argparse
import os

os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {"amdgpu": lambda: gs.amdgpu, "vulkan": lambda: gs.vulkan,
            "cuda": lambda: gs.cuda, "cpu": lambda: gs.cpu}


def aquat(axis, deg):
    a = np.deg2rad(deg) / 2.0
    s = np.sin(a)
    return np.array([np.cos(a), axis[0] * s, axis[1] * s, axis[2] * s])


def qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ])


def euler2quat(rx, ry, rz):
    return qmul(aquat([0, 0, 1], rz), qmul(aquat([0, 1, 0], ry), aquat([1, 0, 0], rx)))


def _np(t):
    return np.asarray(t.cpu() if hasattr(t, "cpu") else t)


def _save_png(arr, path):
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    try:
        from PIL import Image
        Image.fromarray(arr).save(path)
    except Exception:  # noqa: BLE001
        np.save(path.replace(".png", ".npy"), arr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    p.add_argument("--ep", type=int, default=0)
    p.add_argument("--garment-x", type=float, default=0.42)
    p.add_argument("--target-x", type=float, default=0.45)
    p.add_argument("--target-y", type=float, default=0.10)
    p.add_argument("--mesh", default="meshes/cloth.obj")
    p.add_argument("--scale", type=float, default=0.4)
    p.add_argument("--particle-size", type=float, default=0.01)
    # 片状布抓一条边后落地会向 +x 自然铺展; 专家据此补偿, 把夹爪放到 target-offset
    p.add_argument("--offset-x", type=float, default=0.33)
    p.add_argument("--offset-y", type=float, default=0.0)
    p.add_argument("--tol", type=float, default=0.15)
    p.add_argument("--render", action="store_true")
    p.add_argument("--out", default="output/feature5/ep")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    target = np.array([args.target_x, args.target_y])
    place_xy = np.array([args.target_x - args.offset_x, args.target_y - args.offset_y])

    gs.init(backend=BACKENDS[args.backend]())
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=args.particle_size,
            max_stretch_solver_iterations=8, max_bending_solver_iterations=4),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    scene.add_entity(gs.morphs.Box(size=(0.07, 0.07, 0.004),
                                   pos=(args.target_x, args.target_y, 0.002), fixed=True))
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=args.mesh, scale=args.scale,
                       pos=(args.garment_x, 0.0, 0.55), euler=(90.0, 0.0, 0.0)),
        material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=1e-4,
                                        static_friction=0.6, kinetic_friction=0.6),
    )
    cam = scene.add_camera(res=(640, 480), pos=(1.5, 1.2, 0.9), lookat=(0.5, 0.0, 0.35),
                           fov=50, GUI=False)
    scene.build()

    motors, fingers = np.arange(7), np.arange(7, 9)
    franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
    franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))
    hand = franka.get_link("hand")
    lf, rf = franka.get_link("left_finger"), franka.get_link("right_finger")
    q_home = _np(franka.get_dofs_position()).copy()

    pos0 = _np(cloth.get_particles_pos())
    top_idx = np.nonzero(pos0[:, 2] >= pos0[:, 2].max() - 0.012)[0].astype(np.int32)
    cloth.fix_particles(particles_idx_local=top_idx)

    fid = {"n": 0}
    zmax_track = {"v": -1e9}

    def snap():
        if not args.render:
            return
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"frame_{fid['n']:05d}.png"))
        fid["n"] += 1

    def ik(pos, quat, w=0.04):
        q = _np(franka.inverse_kinematics(link=hand, pos=np.array(pos), quat=np.array(quat)))
        q = q.copy(); q[-2:] = w
        return q

    def track():
        zmax_track["v"] = max(zmax_track["v"], float(_np(cloth.get_particles_pos())[:, 2].max()))

    for i in range(280):
        franka.control_dofs_position(q_home[:7], motors)
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if i % 6 == 0:
            snap()

    cp = _np(cloth.get_particles_pos())
    x_min = cp[:, 0].min()
    z_grasp = cp[:, 2].min() + 0.50 * (cp[:, 2].max() - cp[:, 2].min())
    corner = np.array([x_min + 0.015, 0.0, z_grasp])
    safe = np.array([x_min - 0.16, 0.0, z_grasp])

    best = None
    grid = (0, 45, 90, 135, 180, 225, 270, 315)
    for rx in grid:
        for ry in grid:
            for rz in grid:
                quat = euler2quat(rx, ry, rz)
                try:
                    q = ik(safe, quat, 0.04)
                except Exception:  # noqa: BLE001
                    continue
                franka.set_dofs_position(q, zero_velocity=True)
                hp = _np(hand.get_pos())
                if np.linalg.norm(hp - safe) > 0.04:
                    continue
                lp, rp = _np(lf.get_pos()), _np(rf.get_pos())
                approach = 0.5 * (lp + rp) - hp
                approach = approach / (np.linalg.norm(approach) + 1e-9)
                fsep = (lp - rp) / (np.linalg.norm(lp - rp) + 1e-9)
                if approach[0] < 0.85 or abs(approach[2]) > 0.3:
                    continue
                score = abs(fsep[1])
                if best is None or score > best[0]:
                    best = (score, quat)
    if best is None:
        print(f"[f5-ep] ep={args.ep} garment_x={args.garment_x} target=({args.target_x},{args.target_y}) "
              f"success=False place_err=nan grasp_err=nan lifted=False finite=True reason=no_quat")
        return
    gquat = best[1]
    franka.set_dofs_position(ik(safe, gquat, 0.04), zero_velocity=True)
    scene.step(); snap()

    def goto(target_xyz, w, steps, force=None):
        qg = ik(target_xyz, gquat, w)
        qc = _np(franka.get_dofs_position()).copy()
        for s in range(steps):
            a = (s + 1) / steps
            qt = (1 - a) * qc + a * qg
            franka.control_dofs_position(qt[:7], motors)
            if force is None:
                franka.control_dofs_position(np.array([w, w]), fingers)
            else:
                franka.control_dofs_force(np.array([force, force]), fingers)
            scene.step()
            track()
            if s % 6 == 0:
                snap()

    def dwell(steps, force):
        q = _np(franka.get_dofs_position()).copy()
        for s in range(steps):
            franka.control_dofs_position(q[:7], motors)
            franka.control_dofs_force(np.array([force, force]), fingers)
            scene.step()
            track()
            if s % 6 == 0:
                snap()

    goto(safe, 0.04, 180)
    goto(corner, 0.04, 180)
    q_close = ik(corner, gquat, 0.0)[:7]
    for s in range(230):
        franka.control_dofs_position(q_close, motors)
        franka.control_dofs_force(np.array([-4.0, -4.0]), fingers)
        scene.step()
        if s % 6 == 0:
            snap()

    tip_mid = 0.5 * (_np(lf.get_pos()) + _np(rf.get_pos()))
    cp_now = _np(cloth.get_particles_pos())
    grasped = np.nonzero(np.linalg.norm(cp_now - tip_mid, axis=1) < 0.05)[0].astype(np.int32)
    if grasped.size == 0:
        grasped = np.argsort(np.linalg.norm(cp_now - tip_mid, axis=1))[:6].astype(np.int32)
    cloth.fix_particles_to_link(link_idx=hand.idx, particles_idx_local=grasped)
    cloth.release_particle(particles_idx_local=top_idx)

    # 温柔放置: 适度抬起 → 移到目标 → 下降到低位, 每段 dwell 消摆 → 低位松开
    goto(corner + np.array([0, 0, 0.16]), 0.0, 300, force=-4.0)
    dwell(90, -4.0)
    goto(np.array([place_xy[0], place_xy[1], z_grasp + 0.16]), 0.0, 350, force=-4.0)
    dwell(90, -4.0)
    goto(np.array([place_xy[0], place_xy[1], 0.30]), 0.0, 300, force=-4.0)
    dwell(90, -4.0)
    cloth.release_particle(particles_idx_local=grasped)
    for s in range(180):
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if s % 6 == 0:
            snap()

    cp2 = _np(cloth.get_particles_pos())
    finite = bool(np.isfinite(cp2).all())
    centroid = cp2[:, :2].mean(axis=0) if finite else np.array([np.nan, np.nan])
    grasp_xy = cp2[grasped, :2].mean(axis=0) if finite else np.array([np.nan, np.nan])
    place_err = float(np.linalg.norm(centroid - target)) if finite else float("nan")
    grasp_err = float(np.linalg.norm(grasp_xy - target)) if finite else float("nan")
    lifted = bool(zmax_track["v"] - pos0[:, 2].min() > 0.10)
    success = bool(finite and lifted and place_err < args.tol)
    print(f"[f5-ep] ep={args.ep} garment_x={args.garment_x} target=({args.target_x},{args.target_y}) "
          f"success={success} place_err={place_err:.4f} grasp_err={grasp_err:.4f} lifted={lifted} "
          f"finite={finite} centroid=({centroid[0]:.3f},{centroid[1]:.3f})")


if __name__ == "__main__":
    main()
