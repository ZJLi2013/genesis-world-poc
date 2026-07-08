"""feature9: 布料折叠任务(单 fold/进程) + 折叠质量指标。

范式(借 SoftGym ClothFold / Cloth-Funnels): 平铺布 → 抓远边两角 → 抬起 → 平移到近边上方
→ 下降 → 松开 → 远半盖到近半(对折)。抓取原语用 attach(fix_particles_to_link), 因 genesis 1.1.1
无 CouplerOptions 物理夹持(见 part9-exp Exp9.0); attach 在 feature3/4 已证稳定。

折叠质量指标(非落点):
  footprint_ratio = 折后 XY 包围盒面积 / 折前     (单折理论≈0.5, 两折≈0.25)
  coverage        = 移动半(初始 x>x_center)最终 XY 落在静止半最终 XY 包围盒内的比例 (>0.8 佳)
  fold_err        = 移动半与静止半最终质心 x 距离 (越小越对齐)
  flatness        = 折后 z 高度 (越低越平)
success = coverage>tol_cov 且 finite 且(视觉无尖刺, 人工核对)。

用法:
    python scripts/60_cloth_fold.py --mesh meshes/cloth.obj --scale 0.4 --ep 1 \
        --out output/feature9/towel1 [--render]
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


def bbox_area(xy):
    lo = xy.min(axis=0)
    hi = xy.max(axis=0)
    return float((hi[0] - lo[0]) * (hi[1] - lo[1]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    p.add_argument("--ep", type=int, default=0)
    p.add_argument("--cloth-x", type=float, default=0.45)   # 布中心 x
    p.add_argument("--mesh", default="meshes/cloth.obj")
    p.add_argument("--scale", type=float, default=0.4)
    p.add_argument("--particle-size", type=float, default=0.01)
    p.add_argument("--edge-margin", type=float, default=0.05)  # 抓远边条带宽度(x>=x_max-margin)
    p.add_argument("--lift-z", type=float, default=0.24)    # 弧顶高度(远半绕折线翻过去)
    p.add_argument("--lay-z", type=float, default=0.13)     # 铺下高度(边刚好落地, 不怼地)
    p.add_argument("--tol-cov", type=float, default=0.8)
    p.add_argument("--render", action="store_true")
    p.add_argument("--out", default="output/feature9/fold")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

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
    # 平铺布: 水平放置(euler 0), 低空落地自然铺平
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=args.mesh, scale=args.scale,
                       pos=(args.cloth_x, 0.0, 0.03), euler=(0.0, 0.0, 0.0)),
        # bending 深入软区(feature2: 需 ≳1e-2)才能折得动且保住折痕; 偏硬会弹回平铺
        material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=1e-2,
                                        static_friction=0.5, kinetic_friction=0.5),
    )
    cam = scene.add_camera(res=(640, 480), pos=(1.5, 1.2, 1.0), lookat=(0.45, 0.0, 0.05),
                           fov=50, GUI=False)
    scene.build()

    motors, fingers = np.arange(7), np.arange(7, 9)
    franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
    franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))
    hand = franka.get_link("hand")
    q_home = _np(franka.get_dofs_position()).copy()

    fid = {"n": 0}

    def snap():
        if not args.render:
            return
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"frame_{fid['n']:05d}.png"))
        fid["n"] += 1

    def keysnap(name):
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"key_{name}.png"))

    # 候选末端朝向(含 top-down 与倾斜), 用于挑一个"全 waypoint 都可达"的固定朝向
    cand_quats = [euler2quat(180, 0, z) for z in (0, 90, 45, 135, -45)] + \
                 [euler2quat(180, ry, 0) for ry in (20, -20, 40)] + \
                 [euler2quat(150, 0, 0), euler2quat(160, 0, 90)]

    def ik_solve(pos, q4, w=0.04):
        """仅解 IK, 不瞬移(不扰动布)。"""
        try:
            q = _np(franka.inverse_kinematics(link=hand, pos=np.array(pos), quat=q4))
        except Exception:  # noqa: BLE001
            return None
        q = q.copy(); q[-2:] = w
        return q

    def ik_verify(pos, q4, w=0.04):
        """解 IK + 瞬移验证可达; 返回 qpos 或 None。只对布上方的高位点调用(瞬移不扰布)。"""
        q = ik_solve(pos, q4, w)
        if q is None:
            return None
        franka.set_dofs_position(q, zero_velocity=True)
        if np.linalg.norm(_np(hand.get_pos()) - np.array(pos)) < 0.05:
            return q
        return None

    # 铺平静置
    for i in range(320):
        franka.control_dofs_position(q_home[:7], motors)
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if i % 8 == 0:
            snap()

    pos0 = _np(cloth.get_particles_pos())
    xy0 = pos0[:, :2]
    x_center = float(np.median(pos0[:, 0]))
    stat_mask = pos0[:, 0] <= x_center        # 静止半(近边, x 小)
    move_mask = pos0[:, 0] > x_center         # 移动半(远边, x 大) → 折过去
    footprint_before = bbox_area(xy0)

    x_max = float(pos0[:, 0].max())
    # 抓整条远边(x>=x_max-margin), 比只抓两角折得更干净(等价夹条/双手)
    corner_idx = np.nonzero(pos0[:, 0] >= x_max - args.edge_margin)[0].astype(np.int32)
    if corner_idx.size == 0:
        print(f"[f9] ep={args.ep} success=False reason=no_corner_particles")
        return

    x_near = float(pos0[stat_mask, 0].min())
    x_mid = 0.5 * (x_max + x_near)   # 折线(crease)
    grasp_z = 0.12  # 抬高下手, 避免 fingers 撞地把手臂顶偏(attach 用, 不需贴地)
    # 翻页式对折: 远边经折线正上方弧顶翻转 180° 落到近边(而非举高平移成竖直悬挂)
    wp_pos = {
        "above": [x_max, 0.0, 0.32],   # 远边正上方高位(先到这, 再竖直下降, 避免横扫布)
        "grasp": [x_max, 0.0, grasp_z],
        "arc":   [x_mid, 0.0, args.lift_z],   # 弧顶在折线正上方
        "lay":   [x_near, 0.0, args.lay_z],
        "upnear": [x_near, 0.0, 0.35],        # 近边正上方(松手后竖直退刀, 不扫回折好的布)
    }
    # 选朝向: 只对高位点(lift/fold, 在布上方)瞬移验证可达; grasp/lay 在其正下方, 直接取 IK 解
    # (不瞬移 → 不扫过布)。这样整个规划阶段无任何低位瞬移, 布保持平铺不被扰动。
    gquat, wp_q = None, None
    for q4 in cand_quats:
        q_above = ik_verify(wp_pos["above"], q4, 0.04)
        q_arc = ik_verify(wp_pos["arc"], q4, 0.04)
        q_upnear = ik_verify(wp_pos["upnear"], q4, 0.04)
        if q_above is None or q_arc is None or q_upnear is None:
            continue
        q_grasp = ik_solve(wp_pos["grasp"], q4, 0.04)
        q_lay = ik_solve(wp_pos["lay"], q4, 0.04)
        if q_grasp is None or q_lay is None:
            continue
        gquat = q4
        wp_q = {"above": q_above, "grasp": q_grasp, "arc": q_arc,
                "lay": q_lay, "upnear": q_upnear}
        break
    if gquat is None:
        print(f"[f9] ep={args.ep} success=False reason=no_reachable_orientation")
        return
    franka.set_dofs_position(q_home, zero_velocity=True)  # 归位, 从 home 平滑下手

    # 运动学控制: 沿预解 qpos 平滑插值, 每步 set_dofs_position(无 PD 下垂, 手精确到位);
    # 布靠 attach 跟随。路径单调平滑(grasp→lift→fold→lay), 不会像枚举乱姿态那样甩穿布。
    def move_to(qg, w, steps):
        qg = qg.copy(); qg[-2:] = w
        qc = _np(franka.get_dofs_position()).copy(); qc[-2:] = w
        for s in range(steps):
            a = (s + 1) / steps
            qt = (1 - a) * qc + a * qg
            franka.set_dofs_position(qt, zero_velocity=True)
            scene.step()
            if s % 8 == 0:
                snap()

    def dwell(qg, w, steps):
        qg = qg.copy(); qg[-2:] = w
        for s in range(steps):
            franka.set_dofs_position(qg, zero_velocity=True)
            scene.step()
            if s % 8 == 0:
                snap()

    # 下手到远边中点上方低位 → attach → 抬起 → 对折平移 → 铺下 → 松开
    print(f"[dbg] gquat_ok corners={corner_idx.size} x_max={x_max:.3f} x_near={x_near:.3f}")
    move_to(wp_q["above"], 0.04, 160)   # 先到远边正上方高位
    move_to(wp_q["grasp"], 0.04, 140)   # 再竖直下降到 grasp(不横扫布)
    dwell(wp_q["grasp"], 0.04, 60)
    # metrics baseline 用 attach 前的干净平铺态(朝向搜索的瞬移可能微扰), 重算 masks/footprint/corners
    pos0 = _np(cloth.get_particles_pos())
    xy0 = pos0[:, :2]
    x_center = float(np.median(pos0[:, 0]))
    stat_mask = pos0[:, 0] <= x_center
    move_mask = pos0[:, 0] > x_center
    footprint_before = bbox_area(xy0)
    xm, xn = float(pos0[:, 0].max()), float(pos0[:, 0].min())
    corner_idx = np.nonzero(pos0[:, 0] >= xm - args.edge_margin)[0].astype(np.int32)
    xmid = 0.5 * (xm + xn)
    # 钉折线(crease, x≈x_mid 一条窄带): 远半绕折线翻转、近半被锚定, 几何上强制对折
    crease_idx = np.nonzero(np.abs(pos0[:, 0] - xmid) < 0.02)[0].astype(np.int32)
    print(f"[dbg] after grasp hand={_np(hand.get_pos())} cloth_zmax={pos0[:,2].max():.3f} "
          f"corners={corner_idx.size} crease={crease_idx.size}")
    keysnap("settle")
    cloth.fix_particles(particles_idx_local=crease_idx)
    cloth.fix_particles_to_link(link_idx=hand.idx, particles_idx_local=corner_idx)
    move_to(wp_q["arc"], 0.04, 300)    # 经折线弧顶翻转
    print(f"[dbg] after arc hand={_np(hand.get_pos())} cloth_zmax={_np(cloth.get_particles_pos())[:,2].max():.3f}")
    keysnap("arc")
    move_to(wp_q["lay"], 0.04, 260)    # 落到近边(远半盖到近半)
    dwell(wp_q["lay"], 0.04, 120)
    keysnap("lay")
    cloth.release_particle(particles_idx_local=corner_idx)
    # 竖直上抬(近边正上方), 不扫回 x_max 以免把折好的布拖开
    move_to(wp_q["upnear"], 0.04, 140)
    for s in range(140):
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if s % 8 == 0:
            snap()
    keysnap("released")
    cloth.release_particle(particles_idx_local=crease_idx)  # 解折线钉, 整体自然落定
    for s in range(160):
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if s % 8 == 0:
            snap()
    keysnap("final")

    cp = _np(cloth.get_particles_pos())
    finite = bool(np.isfinite(cp).all())
    if not finite:
        print(f"[f9] ep={args.ep} success=False finite=False")
        return
    xyf = cp[:, :2]
    footprint_after = bbox_area(xyf)
    footprint_ratio = footprint_after / (footprint_before + 1e-9)
    stat_xy = xyf[stat_mask]
    move_xy = xyf[move_mask]
    lo, hi = stat_xy.min(axis=0), stat_xy.max(axis=0)
    inside = ((move_xy[:, 0] >= lo[0]) & (move_xy[:, 0] <= hi[0]) &
              (move_xy[:, 1] >= lo[1]) & (move_xy[:, 1] <= hi[1]))
    coverage = float(inside.mean())
    fold_err = float(abs(move_xy[:, 0].mean() - stat_xy[:, 0].mean()))
    flatness = float(cp[:, 2].max() - cp[:, 2].min())
    success = bool(finite and coverage > args.tol_cov)
    print(f"[f9] ep={args.ep} success={success} coverage={coverage:.3f} "
          f"footprint_ratio={footprint_ratio:.3f} fold_err={fold_err:.3f} "
          f"flatness={flatness:.3f} finite={finite} "
          f"footprint_before={footprint_before:.4f} footprint_after={footprint_after:.4f}")


if __name__ == "__main__":
    main()
