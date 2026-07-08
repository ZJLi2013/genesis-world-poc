"""feature3: Franka 夹爪水平抓取悬挂布料（自标定夹爪朝向）。

要点（解决 v1 顶向下穿插爆炸）：
- 布料为竖直窗帘（XZ 平面、法向 Y）；抓其 +X 侧竖边角，避免手掌与布面重叠。
- 夹爪【水平】接近（接近轴≈ -X），手指分离轴沿 Y 骑跨布面两侧。
- 姿态用【自标定】确定：在远离布的安全位枚举候选 quat 瞬移，读两指世界坐标，
  选 finger_sep≈Y 且 approach≈-X 的 quat（不靠肉眼猜）。
- 接近用插值控制（非瞬移到位），避免高速扫掠。

用法:
    python scripts/30_franka_grasp_cloth.py --backend amdgpu --out output/feature3/grasp
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


def euler2quat(rx, ry, rz):  # 外旋 xyz => qz*qy*qx
    return qmul(aquat([0, 0, 1], rz), qmul(aquat([0, 1, 0], ry), aquat([1, 0, 0], rx)))


def _save_png(arr, path):
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    try:
        from PIL import Image
        Image.fromarray(arr).save(path)
    except Exception:  # noqa: BLE001
        np.save(path.replace(".png", ".npy"), arr)


def _np(t):
    return np.asarray(t.cpu() if hasattr(t, "cpu") else t)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    p.add_argument("--scale", type=float, default=0.4)
    p.add_argument("--out", default="output/feature3/grasp")
    p.add_argument("--render-every", type=int, default=6, help="每隔几步出一帧(视频用)")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    gs.init(backend=BACKENDS[args.backend]())
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=0.01, max_stretch_solver_iterations=8, max_bending_solver_iterations=4
        ),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    cloth = scene.add_entity(
        gs.morphs.Mesh(file="meshes/cloth.obj", scale=args.scale,
                       pos=(0.40, 0.0, 0.55), euler=(90.0, 0.0, 0.0)),
        material=gs.materials.PBD.Cloth(stretch_compliance=1e-7, bending_compliance=1e-4,
                                        static_friction=0.6, kinetic_friction=0.6),
    )
    cam = scene.add_camera(res=(640, 480), pos=(1.4, 1.1, 0.9), lookat=(0.4, 0.0, 0.5),
                           fov=45, GUI=False)
    scene.build()

    motors = np.arange(7)
    fingers = np.arange(7, 9)
    franka.set_dofs_kp(np.array([4500, 4500, 3500, 3500, 2000, 2000, 2000, 100, 100]))
    franka.set_dofs_kv(np.array([450, 450, 350, 350, 200, 200, 200, 10, 10]))
    hand = franka.get_link("hand")
    lf = franka.get_link("left_finger")
    rf = franka.get_link("right_finger")
    q_home = _np(franka.get_dofs_position()).copy()

    # 固定布料顶边 → 竖直悬挂成窗帘（否则会摊到地板上）
    pos0 = _np(cloth.get_particles_pos())
    ztop = pos0[:, 2].max()
    top_idx = np.nonzero(pos0[:, 2] >= ztop - 0.012)[0].astype(np.int32)
    cloth.fix_particles(particles_idx_local=top_idx)
    print(f"[grasp] cloth particles={pos0.shape[0]} pinned_top={top_idx.size}")

    def render(tag):
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"{tag}.png"))

    _frame = {"n": 0}
    re = max(1, args.render_every)

    def snap():
        rgb = cam.render(rgb=True)
        arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
        _save_png(arr, os.path.join(args.out, f"frame_{_frame['n']:05d}.png"))
        _frame["n"] += 1

    def cstat(tag):
        cp = _np(cloth.get_particles_pos())
        ok = bool(np.isfinite(cp).all())
        zmax = cp[:, 2].max() if ok else float("nan")
        print(f"[phase] {tag:14s} finite={ok} cloth_zmax={zmax:.4f}")
        return ok

    def ik(pos, quat, w=0.04):
        q = _np(franka.inverse_kinematics(link=hand, pos=np.array(pos), quat=np.array(quat)))
        q = q.copy(); q[-2:] = w
        return q

    # 0) 布料静置
    for i in range(250):
        franka.control_dofs_position(q_home[:7], motors)
        franka.control_dofs_position(np.array([0.04, 0.04]), fingers)
        scene.step()
        if i % re == 0:
            snap()
    render("00_settle")
    cstat("settle_only")

    cp = _np(cloth.get_particles_pos())
    x_max, x_min = cp[:, 0].max(), cp[:, 0].min()
    z_max, z_min = cp[:, 2].max(), cp[:, 2].min()
    z_grasp = z_min + 0.50 * (z_max - z_min)
    # 抓【近端 -X 竖边】：离机器人更近(可达)，且水平接近时手掌停在布的 x 外侧→不重叠
    corner = np.array([x_min + 0.015, 0.0, z_grasp])           # 抓取目标
    pre = np.array([x_min - 0.16, 0.0, z_grasp])               # 预抓取（布外侧）
    safe = np.array([x_min - 0.16, 0.0, z_grasp])              # 标定/安全位
    print(f"[grasp] cloth x=[{x_min:.3f},{x_max:.3f}] z=[{z_min:.3f},{z_max:.3f}] "
          f"z_grasp={z_grasp:.3f} pre_dist={np.linalg.norm(pre):.3f}")

    # 1) 自标定夹爪朝向：枚举候选 quat，在 safe 位瞬移读手指轴。
    #    硬性要求【水平 +X 接近】(approach·+X>0.85, |z|<0.3)，再最大化手指沿 Y。
    best = None
    grid = (0, 45, 90, 135, 180, 225, 270, 315)
    for rx in grid:
        for ry in grid:
            for rz in grid:
                quat = euler2quat(rx, ry, rz)
                try:
                    q = ik(safe, quat, w=0.04)
                except Exception:  # noqa: BLE001
                    continue
                franka.set_dofs_position(q, zero_velocity=True)  # 仅运动学，不 step → 不碰布
                hp = _np(hand.get_pos())
                if np.linalg.norm(hp - safe) > 0.04:   # IK 没到位，跳过
                    continue
                lp, rp = _np(lf.get_pos()), _np(rf.get_pos())
                tip_mid = 0.5 * (lp + rp)
                approach = tip_mid - hp
                approach = approach / (np.linalg.norm(approach) + 1e-9)
                fsep = lp - rp
                fsep = fsep / (np.linalg.norm(fsep) + 1e-9)
                if approach[0] < 0.85 or abs(approach[2]) > 0.3:   # 必须水平朝 +X
                    continue
                score = abs(fsep[1])                    # 手指沿 Y 越好
                if best is None or score > best[0]:
                    best = (score, quat, (rx, ry, rz), approach.copy(), fsep.copy())
    if best is None:
        print("[grasp] no feasible horizontal quat found"); return
    score, gquat, geuler, approach, fsep = best
    print(f"[grasp] best euler={geuler} score={score:.3f} approach={approach.round(2)} "
          f"finger_sep={fsep.round(2)}")

    # 回到 safe 位（已是 best quat）并渲染确认朝向
    franka.set_dofs_position(ik(safe, gquat, 0.04), zero_velocity=True)
    scene.step(); render("01_safe_calib"); snap(); cstat("after_settle")

    def goto(target, w, steps):
        q_goal = ik(target, gquat, w)
        q_cur = _np(franka.get_dofs_position()).copy()
        for s in range(steps):
            a = (s + 1) / steps
            q_t = (1 - a) * q_cur + a * q_goal
            franka.control_dofs_position(q_t[:7], motors)
            franka.control_dofs_position(np.array([w, w]), fingers)
            scene.step()
            if s % re == 0:
                snap()

    # 2) 移到预抓取位（布外侧，手指张开）
    goto(pre, 0.04, 200); cstat("after_pre")
    # 3) 水平靠近，把竖边角送入两指之间
    goto(corner, 0.04, 200); cstat("after_approach")
    z_before = _np(cloth.get_particles_pos())[:, 2].copy()
    # 4) 闭合手指（缓慢、低力，避免 PBD 接触崩飞）
    q_close = ik(corner, gquat, 0.0)[:7]
    for s in range(250):
        franka.control_dofs_position(q_close, motors)
        franka.control_dofs_force(np.array([-4.0, -4.0]), fingers)
        scene.step()
        if s % re == 0:
            snap()
    cstat("after_close")
    fcontact = _np(franka.get_links_net_contact_force())

    # 4b) 抓取区粒子绑到夹爪 link（保证拎得起，类比 LeHome 的 attach）+ 解钉顶边
    tip_mid = 0.5 * (_np(lf.get_pos()) + _np(rf.get_pos()))
    cp_now = _np(cloth.get_particles_pos())
    grasped = np.nonzero(np.linalg.norm(cp_now - tip_mid, axis=1) < 0.05)[0].astype(np.int32)
    if grasped.size == 0:  # 兜底：取最近的几颗
        grasped = np.argsort(np.linalg.norm(cp_now - tip_mid, axis=1))[:6].astype(np.int32)
    cloth.fix_particles_to_link(link_idx=hand.idx, particles_idx_local=grasped)
    cloth.release_particle(particles_idx_local=top_idx)   # 解钉顶边
    print(f"[grasp] attached={grasped.size} to hand(link {hand.idx}); released top={top_idx.size}")

    # 5) 拎起（顶边已松，整块布靠夹爪承载）
    cur = _np(franka.get_dofs_position()).copy()
    q_lift = ik(corner + np.array([0, 0, 0.28]), gquat, 0.0)
    for s in range(500):
        a = (s + 1) / 500
        q_t = (1 - a) * cur + a * q_lift
        franka.control_dofs_position(q_t[:7], motors)
        franka.control_dofs_force(np.array([-4.0, -4.0]), fingers)
        scene.step()
        if s % re == 0:
            snap()
    for _ in range(60):   # 顶部停留，展示稳定悬挂
        franka.control_dofs_position(q_lift[:7], motors)
        franka.control_dofs_force(np.array([-4.0, -4.0]), fingers)
        scene.step()
        if _ % re == 0:
            snap()
    cstat("after_lift")

    cp2 = _np(cloth.get_particles_pos())
    finite = bool(np.isfinite(cp2).all())
    near = np.nonzero(np.linalg.norm(cp[:, [0, 2]] - corner[[0, 2]], axis=1) < 0.06)[0]
    dz = float(cp2[near, 2].mean() - z_before[near].mean()) if near.size else float("nan")
    zmin_rise = float(cp2[:, 2].min() - z_before.min())   # 整块布最低点抬升→真被拎起
    print(f"[grasp-metric] finite={finite} near={near.size} grasp_region_dz={dz:.4f} "
          f"cloth_zmin_rise={zmin_rise:.4f} cloth_zmax={cp2[:,2].max():.4f} "
          f"max_finger_contact={np.abs(fcontact).max():.4f}")


if __name__ == "__main__":
    main()
