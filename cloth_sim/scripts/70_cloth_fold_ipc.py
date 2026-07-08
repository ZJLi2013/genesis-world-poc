"""feature10 Exp 10.2 — IPC/FEM cloth fold, PBD(AMD) vs IPC(NV) 对照.

核心问题: AMD 上 PBD 布对折"松手回弹平铺"(footprint_ratio≈1.0). NV 上用
IPC coupler + FEM.Cloth(NeoHookeanShell) + 精确摩擦自接触, 松手后能否"保住对折"
(footprint_ratio<1)?

机制(不依赖机器人臂, 隔离布料物理本身):
  用 Genesis FEM 的 set_vertex_constraints / update_constraint_targets /
  remove_vertex_constraints 作为"运动学抓手": 钉住远半顶点, 沿弧线把它们镜像翻折
  盖到近半上, 松开(remove), 静置, 测 footprint_ratio / coverage / flatness.
"""
import argparse
import os
import time
import numpy as np

from huggingface_hub import snapshot_download
import genesis as gs


def to_np(v):
    try:
        import torch
        if isinstance(v, torch.Tensor):
            return v.detach().cpu().numpy()
    except Exception:
        pass
    return np.asarray(v)


def cloth_pos(entity):
    return to_np(entity.get_state().pos).reshape(-1, 3)


def bbox_xy_area(p):
    dx = p[:, 0].max() - p[:, 0].min()
    dy = p[:, 1].max() - p[:, 1].min()
    return float(dx * dy), float(dx), float(dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="gpu", choices=["gpu", "cpu"])
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--z0", type=float, default=0.05, help="cloth rest height above plane")
    ap.add_argument("--fold-steps", type=int, default=80)
    ap.add_argument("--settle-steps", type=int, default=120)
    ap.add_argument("--layer-gap", type=float, default=0.02)
    ap.add_argument("--arc-h", type=float, default=0.25, help="arc apex height while folding")
    ap.add_argument("--E", type=float, default=1e4)
    ap.add_argument("--bend", type=float, default=1.0, help="bending_stiffness (low=less springback)")
    ap.add_argument("--contact-dhat", type=float, default=0.004)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--diag", action="store_true", help="build, print cloth bbox/orientation, exit")
    ap.add_argument("--out", default="output/feature10/fold_ipc")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu, logging_level="warning")

    # FEM.Cloth (NeoHookean shell) is only simulated via the IPC coupler in 1.2.1
    # (native FEM solver has no shell energy-gradient; set_vertex_constraints is also
    # blocked under IPC). So we drive the fold kinematically with entity.set_position
    # (whole-mesh target) under the IPC coupler, then stop driving and let it settle.
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.02),
        coupler_options=gs.options.IPCCouplerOptions(
            contact_d_hat=args.contact_dhat, two_way_coupling=True),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(coup_type="ipc_only"))

    asset = snapshot_download(
        repo_type="dataset", repo_id="Genesis-Intelligence/assets",
        revision="8aa8fcd60500b9f3a36c356080224bdb1be9ee59",
        allow_patterns="IPC/grid20x20.obj", max_workers=1)
    cloth = scene.add_entity(
        # grid20x20 rests in XZ plane by default -> rotate 90° about X to lay flat in XY
        morph=gs.morphs.Mesh(file=f"{asset}/IPC/grid20x20.obj", scale=args.scale,
                             pos=(0.0, 0.0, args.z0), euler=(90.0, 0.0, 0.0)),
        material=gs.materials.FEM.Cloth(E=args.E, nu=0.499, rho=200,
                                        thickness=0.001, bending_stiffness=args.bend,
                                        friction_mu=0.5),
    )

    cam = None
    if args.render:
        cam = scene.add_camera(res=(640, 480), pos=(1.2, 1.0, 0.9),
                               lookat=(0.0, 0.0, 0.05), fov=45, GUI=False)

    scene.build(n_envs=1)

    frames = []

    def snap():
        if cam is not None:
            rgb = cam.render()[0]
            frames.append(np.asarray(rgb)[:, :, :3].astype(np.uint8))

    # let cloth settle flat first
    for _ in range(30):
        scene.step()
        snap()

    P = cloth_pos(cloth)
    xmid = 0.5 * (P[:, 0].max() + P[:, 0].min())
    if args.diag:
        area, dx, dy = bbox_xy_area(P)
        print(f"[diag] nverts={P.shape[0]} x=[{P[:,0].min():.3f},{P[:,0].max():.3f}] "
              f"y=[{P[:,1].min():.3f},{P[:,1].max():.3f}] z=[{P[:,2].min():.3f},{P[:,2].max():.3f}] "
              f"bbox_area={area:.4f} xmid={xmid:.3f}")
        return

    area0, dx0, dy0 = bbox_xy_area(P)

    # far half = verts with x > xmid ; fold them mirrored across xmid onto near half.
    # whole-mesh target for set_position: near half stays, far half arcs over to folded.
    far = P[:, 0] > xmid + 1e-6
    start = P.copy()
    folded = P.copy()
    folded[far, 0] = 2.0 * xmid - P[far, 0]           # mirror across fold line
    folded[far, 2] = args.z0 + args.layer_gap          # land on top of near half

    # kinematically drive to folded over fold_steps (arc apex so far half turns over)
    for s in range(args.fold_steps):
        t = (s + 1) / args.fold_steps
        cur = (1 - t) * start + t * folded
        cur[far, 2] += args.arc_h * np.sin(np.pi * t)  # arc apex only on far half
        cloth.set_position(cur)
        scene.step()
        snap()

    # stop driving -> free. settle under gravity + IPC friction self-contact.
    for _ in range(args.settle_steps):
        scene.step()
        snap()

    Pf = cloth_pos(cloth)
    area1, dx1, dy1 = bbox_xy_area(Pf)
    finite = bool(np.isfinite(Pf).all())
    footprint_ratio = area1 / area0 if area0 > 0 else float("nan")
    zspan = float(Pf[:, 2].max() - Pf[:, 2].min())

    # coverage: fraction of far-half verts whose XY now lies within near-half XY bbox
    near = np.where(P[:, 0] <= xmid + 1e-6)[0]
    nx0, nx1 = P[near, 0].min(), P[near, 0].max()
    ny0, ny1 = P[near, 1].min(), P[near, 1].max()
    fx, fy = Pf[far, 0], Pf[far, 1]
    inside = (fx >= nx0) & (fx <= nx1) & (fy >= ny0) & (fy <= ny1)
    coverage = float(inside.mean()) if far.size else float("nan")

    print(f"[f10.2] backend={args.backend} finite={finite} footprint_ratio={footprint_ratio:.3f} "
          f"coverage={coverage:.3f} zspan={zspan:.3f} area0={area0:.4f} area1={area1:.4f} "
          f"dx {dx0:.3f}->{dx1:.3f} dy {dy0:.3f}->{dy1:.3f} frames={len(frames)}")

    if args.render and frames:
        import imageio
        vid = os.path.join(args.out, "fold_ipc.mp4")
        w = imageio.get_writer(vid, fps=30)
        for f in frames:
            w.append_data(f)
        w.close()
        print("[f10.2] video:", vid, "frames", len(frames))
    print("[f10.2] DONE")


if __name__ == "__main__":
    main()
