"""M0b pose generator -- extract REAL camera poses from a Genesis scene.

Runs inside the Genesis container (CPU backend, headless). Zero GPU:
    PYOPENGL_PLATFORM=egl python m0b_genesis_poses.py --mode orbit --out poses.json

Two modes, both dump a list of {frame, pos, lookat, up} in Genesis (Z-up) world:
  orbit : free camera (scene.add_camera) swept along a Z-up orbit via set_pose;
          reads back Genesis' orthonormalized cam.pos/lookat/up.
  wrist : camera attach()'d to the Franka `hand` link; a joint is swept via
          set_dofs_position, then move_to_attach() derives the wrist-cam pose
          from forward kinematics.
"""
import argparse
import json
import numpy as np


def _v3(x):
    return np.asarray(x).reshape(-1)[:3].astype(float).tolist()


def gen_orbit(n, radius, height, center):
    import genesis as gs
    gs.init(backend=gs.cpu)
    scene = gs.Scene(show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    cam = scene.add_camera(res=(1280, 720), pos=(radius, 0.0, height),
                           lookat=tuple(center), up=(0.0, 0.0, 1.0), fov=60, GUI=False)
    scene.build()
    poses = []
    for i in range(n):
        a = 2.0 * np.pi * i / n
        eye = (center[0] + radius * np.cos(a),
               center[1] + radius * np.sin(a),
               center[2] + height)
        cam.set_pose(pos=eye, lookat=tuple(center), up=(0.0, 0.0, 1.0))
        poses.append({"frame": i, "pos": _v3(cam.pos),
                      "lookat": _v3(cam.lookat), "up": _v3(cam.up)})
    return poses


def gen_wrist(n):
    import genesis as gs
    gs.init(backend=gs.cpu)
    scene = gs.Scene(show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    cam = scene.add_camera(res=(1280, 720), pos=(1.0, 0.0, 1.0),
                           lookat=(0.0, 0.0, 0.5), up=(0.0, 0.0, 1.0), fov=60, GUI=False)
    scene.build()
    try:
        hand = franka.get_link("hand")
    except Exception:
        hand = franka.links[-1]
    offset_T = np.eye(4)
    offset_T[:3, 3] = [0.05, 0.0, 0.05]
    cam.attach(hand, offset_T)
    poses = []
    n_dofs = franka.n_dofs
    for i in range(n):
        q = np.zeros(n_dofs)
        # sweep shoulder+elbow so the wrist (hence camera) traces a real arc
        t = i / max(n - 1, 1)
        if n_dofs > 3:
            q[1] = -1.2 + 1.6 * t
            q[3] = -2.2 + 1.2 * t
        franka.set_dofs_position(q)
        scene.step()
        cam.move_to_attach()
        poses.append({"frame": i, "pos": _v3(cam.pos),
                      "lookat": _v3(cam.lookat), "up": _v3(cam.up)})
    return poses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["orbit", "wrist"], default="orbit")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--radius", type=float, default=9.0)
    ap.add_argument("--height", type=float, default=2.0)
    ap.add_argument("--center", type=float, nargs=3, default=[0.0, 0.0, 0.0])
    ap.add_argument("--out", default="/tmp/genesis_poses.json")
    args = ap.parse_args()

    if args.mode == "orbit":
        poses = gen_orbit(args.n, args.radius, args.height, args.center)
    else:
        poses = gen_wrist(args.n)

    meta = {"mode": args.mode, "frame_up": "z", "world": "genesis", "poses": poses}
    with open(args.out, "w") as f:
        json.dump(meta, f, indent=1)
    print(f"WROTE {args.out}  mode={args.mode}  n={len(poses)}")
    for p in poses[:3]:
        print(" ", p)
    print("POSES_OK")


if __name__ == "__main__":
    main()
