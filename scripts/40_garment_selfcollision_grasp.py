"""feature4: 非平面衣物(开口圆筒 tube) 自碰撞稳定性 + 抓取迁移。

Genesis PBD 自碰撞是内禀的(空间哈希, 半径=particle_size, 无独立开关)。本脚本:
- mode=drape: 水平 tube 掉到地面自折叠(前后壁贴合), 量化 finite / penetration_ratio / step_ms。
- mode=grasp: 竖直 tube(筒裙) 钉顶 rim 悬挂, 迁移 feature3 自标定水平抓取 + attach + 解钉 + 拎起。

tube 程序生成(零下载依赖, 可复现); 也支持 --mesh 外部 OBJ 后续换真实衣物。

用法:
    python scripts/40_garment_selfcollision_grasp.py --mode drape --particle-size 0.012 --out output/feature4/drape_ps012
    python scripts/40_garment_selfcollision_grasp.py --mode grasp --out output/feature4/grasp
"""
import argparse
import os
import time

os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {"amdgpu": lambda: gs.amdgpu, "vulkan": lambda: gs.vulkan,
            "cuda": lambda: gs.cuda, "cpu": lambda: gs.cpu}


# ----- 四元数/欧拉 (与 feature3 一致) -----
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


def make_tube_obj(path, r, h, nu, nv, axis):
    """开口圆筒(无端盖)。axis='z' 竖直筒裙; axis='y' 水平筒。"""
    verts = []
    for j in range(nv + 1):
        t = j / nv
        for i in range(nu):
            th = 2 * np.pi * i / nu
            c, s = r * np.cos(th), r * np.sin(th)
            if axis == "z":
                verts.append((c, s, t * h))
            else:
                verts.append((c, (t - 0.5) * h, s))
    faces = []
    for j in range(nv):
        for i in range(nu):
            a = j * nu + i
            b = j * nu + (i + 1) % nu
            cc = (j + 1) * nu + i
            d = (j + 1) * nu + (i + 1) % nu
            faces.append((a, b, d))
            faces.append((a, d, cc))
    with open(path, "w") as f:
        for v in verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for fc in faces:
            f.write(f"f {fc[0]+1} {fc[1]+1} {fc[2]+1}\n")
    return path


def penetration_ratio(pos, ps):
    """非相邻粒子被压到一起的比例。remesh 后正常邻距≈ps, <0.3·ps 即视为穿插/重叠。"""
    n = pos.shape[0]
    thr = 0.3 * ps
    try:
        from scipy.spatial import cKDTree
        pairs = cKDTree(pos).query_pairs(thr, output_type="ndarray")
        return float(len(pairs)) / max(n, 1)
    except Exception:  # noqa: BLE001
        cnt = 0
        for i in range(n):
            d = np.linalg.norm(pos[i + 1:] - pos[i], axis=1)
            cnt += int((d < thr).sum())
        return float(cnt) / max(n, 1)


def build_scene(args, axis, cloth_pos, cloth_euler):
    gs.init(backend=BACKENDS[args.backend]())
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=args.particle_size,
            max_stretch_solver_iterations=8, max_bending_solver_iterations=4,
        ),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    franka = None
    if args.mode == "grasp":
        franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    mesh_file = args.mesh
    if mesh_file is None:
        os.makedirs(args.out, exist_ok=True)
        mesh_file = make_tube_obj(os.path.join(args.out, "tube.obj"),
                                  r=args.radius, h=args.height, nu=44, nv=26, axis=axis)
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=mesh_file, scale=args.scale, pos=cloth_pos, euler=cloth_euler),
        material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=args.bending,
                                        static_friction=0.6, kinetic_friction=0.6),
    )
    cam = scene.add_camera(res=(640, 480), pos=(1.2, 1.1, 0.7), lookat=(0.45, 0.0, 0.25),
                           fov=45, GUI=False)
    scene.build()
    return scene, cloth, franka, cam


def run_drape(args):
    # 软筒从高处掉下 → 落地塌扁/自折叠, 真正压力测试自碰撞
    scene, cloth, _, cam = build_scene(args, axis="y",
                                       cloth_pos=(0.45, 0.0, 0.36), cloth_euler=(20, 0, 0))
    n = _np(cloth.get_particles_pos()).shape[0]
    print(f"[f4-drape] particles={n} particle_size={args.particle_size}")

    def render(tag):
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"{tag}.png"))

    render("00_init")
    t0 = time.perf_counter()
    steps = 600
    for i in range(steps):
        scene.step()
        if i % 80 == 0:
            render(f"step_{i:04d}")
    step_ms = (time.perf_counter() - t0) / steps * 1000.0
    render("99_final")

    pos = _np(cloth.get_particles_pos())
    finite = bool(np.isfinite(pos).all())
    pen = penetration_ratio(pos, args.particle_size) if finite else float("nan")
    thickness = float(pos[:, 2].max() - pos[:, 2].min()) if finite else float("nan")
    print(f"[f4-drape-metric] particle_size={args.particle_size} n={n} finite={finite} "
          f"penetration_ratio={pen:.4f} flatten_thickness={thickness:.4f} step_ms={step_ms:.1f}")


def run_grasp(args):
    # 竖直筒裙, 钉顶 rim 悬挂; 抓取用偏硬布(便于悬挂/抓取)
    args.bending = 1e-4
    scene, cloth, franka, cam = build_scene(args, axis="z",
                                            cloth_pos=(0.42, 0.0, 0.30), cloth_euler=(0, 0, 0))
    motors, fingers = np.arange(7), np.arange(7, 9)
    franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
    franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))
    hand = franka.get_link("hand")
    lf, rf = franka.get_link("left_finger"), franka.get_link("right_finger")
    q_home = _np(franka.get_dofs_position()).copy()

    pos0 = _np(cloth.get_particles_pos())
    ztop = pos0[:, 2].max()
    top_idx = np.nonzero(pos0[:, 2] >= ztop - 0.012)[0].astype(np.int32)
    cloth.fix_particles(particles_idx_local=top_idx)
    print(f"[f4-grasp] particles={pos0.shape[0]} pinned_top_rim={top_idx.size}")

    fid = {"n": 0}

    def snap():
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"frame_{fid['n']:05d}.png"))
        fid["n"] += 1

    def ik(pos, quat, w=0.04):
        q = _np(franka.inverse_kinematics(link=hand, pos=np.array(pos), quat=np.array(quat)))
        q = q.copy(); q[-2:] = w
        return q

    for i in range(300):
        franka.control_dofs_position(q_home[:7], motors)
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if i % 6 == 0:
            snap()

    cp = _np(cloth.get_particles_pos())
    x_min, z_top = cp[:, 0].min(), cp[:, 2].max()
    z_grasp = cp[:, 2].min() + 0.55 * (z_top - cp[:, 2].min())
    corner = np.array([x_min + 0.01, 0.0, z_grasp])
    pre = np.array([x_min - 0.16, 0.0, z_grasp])
    safe = np.array([x_min - 0.16, 0.0, z_grasp])
    print(f"[f4-grasp] x_min={x_min:.3f} z_grasp={z_grasp:.3f} pre_dist={np.linalg.norm(pre):.3f}")

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
                    best = (score, quat, (rx, ry, rz))
    if best is None:
        print("[f4-grasp] no feasible horizontal quat"); return
    gquat = best[1]
    print(f"[f4-grasp] best euler={best[2]}")
    franka.set_dofs_position(ik(safe, gquat, 0.04), zero_velocity=True)
    scene.step(); snap()

    def goto(target, w, steps):
        qg = ik(target, gquat, w)
        qc = _np(franka.get_dofs_position()).copy()
        for s in range(steps):
            a = (s + 1) / steps
            qt = (1 - a) * qc + a * qg
            franka.control_dofs_position(qt[:7], motors)
            franka.control_dofs_position(np.array([w, w]), fingers)
            scene.step()
            if s % 6 == 0:
                snap()

    goto(pre, 0.04, 200)
    goto(corner, 0.04, 200)
    z_before = _np(cloth.get_particles_pos())[:, 2].copy()
    q_close = ik(corner, gquat, 0.0)[:7]
    for s in range(250):
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
    print(f"[f4-grasp] attached={grasped.size}; released_top={top_idx.size}")

    cur = _np(franka.get_dofs_position()).copy()
    q_lift = ik(corner + np.array([0, 0, 0.30]), gquat, 0.0)
    for s in range(500):
        a = (s + 1) / 500
        qt = (1 - a) * cur + a * q_lift
        franka.control_dofs_position(qt[:7], motors)
        franka.control_dofs_force(np.array([-4.0, -4.0]), fingers)
        scene.step()
        if s % 6 == 0:
            snap()

    cp2 = _np(cloth.get_particles_pos())
    finite = bool(np.isfinite(cp2).all())
    zmin_rise = float(cp2[:, 2].min() - z_before.min())
    print(f"[f4-grasp-metric] finite={finite} cloth_zmin_rise={zmin_rise:.4f} "
          f"cloth_zmax={cp2[:,2].max():.4f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    p.add_argument("--mode", default="drape", choices=["drape", "grasp"])
    p.add_argument("--mesh", default=None, help="外部衣物 OBJ; 留空则程序生成 tube")
    p.add_argument("--radius", type=float, default=0.06)
    p.add_argument("--height", type=float, default=0.22)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--bending", type=float, default=1e-2, help="drape 用软区让筒会塌")
    p.add_argument("--particle-size", type=float, default=0.012)
    p.add_argument("--out", default="output/feature4/run")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if args.mode == "drape":
        run_drape(args)
    else:
        run_grasp(args)


if __name__ == "__main__":
    main()
