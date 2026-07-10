"""Render a colored Franka into the 3DGS kitchen (vk_gs side of feature5).

Reads the per-link world poses dumped by `franka_fk_dump.py`, loads the kitchen
splat, instantiates every Franka visual `.obj` colored per its MJCF material,
places each part at its link's splat-space transform, and renders PNG(s).

Two modes, chosen by frame count in the poses JSON:
  - 1 frame  (F1 static)  -> render every named camera preset to <cam>.png
  - N frames (F2 motion)  -> fixed camera, one PNG per frame: <prefix>_0000.png ...

Runs inside the `vkgs_build` container (needs the built `vkgs` module).
`franka_kitchen_common.py` must sit next to this file.

Usage:
    # copy the scripts next to the built module, then:
    python franka_render_kitchen.py --poses /tmp/franka_poses.json --out-dir .
    python franka_render_kitchen.py --poses /tmp/franka_traj.json --cam overview \
        --out-prefix franka_motion --out-dir out
"""
import argparse
import glob
import os
import sys

# camera presets in SPLAT space (feature3 mapping of the workshop cameras;
# see docs/exp/part5-exp.md F1 for the overview-cam derivation).
CAMERAS = {
    "overview": dict(eye=[0.0, -0.125, -0.28], center=[0.0, -0.425, 1.82], up=[0.0, 1.0, 0.0], fovy=65.0),
    "front":    dict(eye=[0.2, -0.5, -0.8],    center=[0.2, -0.9, 0.92],  up=[0.0, 1.0, 0.0], fovy=60.0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", default="/tmp/franka_poses.json",
                    help="JSON from franka_fk_dump.py ({'frames':[{'links':{...}}]})")
    ap.add_argument("--ply", default="/work/assets/rustic_kitchen_2m.ply")
    ap.add_argument("--assets", default="/work/assets/franka", help="dir of Franka visual .obj")
    ap.add_argument("--vkgs-build", default=os.environ.get("VKGS_BUILD", "/work/vk_gaussian_splatting/build"),
                    help="dir containing the built vkgs module")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--out-prefix", default="franka", help="motion mode: PNG name prefix")
    ap.add_argument("--cam", default="overview", choices=list(CAMERAS),
                    help="motion mode: which camera preset to use")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--gpu", type=int, default=1)
    args = ap.parse_args()

    sys.path.insert(0, args.vkgs_build)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import json
    import vkgs
    import franka_kitchen_common as fk

    with open(args.poses) as f:
        frames = json.load(f)["frames"]
    os.makedirs(args.out_dir, exist_ok=True)

    r = vkgs.Renderer(ply=args.ply, width=args.width, height=args.height, gpu=args.gpu)
    print("Renderer OK splat_count", r.splat_count(), "frames", len(frames), flush=True)

    # Instantiate every visual .obj once; remember (mesh_idx, link_name).
    instances = []  # list of (idx, link_name)
    for path in sorted(glob.glob(os.path.join(args.assets, "*.obj"))):
        base = os.path.basename(path)
        if "collision" in base:
            continue
        stem = base[:-4]
        marker = fk.link_of(stem)
        if marker is None:
            print("skip", base, flush=True)
            continue
        col = fk.color_of(stem)
        targets = fk.FINGER_LINKS if marker == "finger" else (marker,)
        for link_name in targets:
            idx = r.add_mesh(path)
            if idx < 0:
                continue
            if col is not None:
                r.set_mesh_color(idx, col)
            instances.append((idx, link_name))
    print("mesh instances", len(instances), "mesh_count", r.mesh_count(), flush=True)

    def apply_frame(frame):
        links = frame["links"]
        for idx, link_name in instances:
            lk = links.get(link_name)
            if lk is None:
                continue
            r.set_mesh_transform(idx, fk.link_transform_flat(lk["pos"], lk["quat"]))

    def shoot(name, cam):
        r.set_camera(eye=cam["eye"], center=cam["center"], up=cam["up"], fovy=cam["fovy"])
        for _ in range(5):
            r.step()
        out = os.path.join(args.out_dir, name + ".png")
        r.save_png(out)
        arr = r.readback()
        print(name, arr.shape, "mean", round(float(arr.mean()), 1), "->", out, flush=True)

    if len(frames) == 1:
        apply_frame(frames[0])
        for cam_name, cam in CAMERAS.items():
            shoot("%s_%s" % (args.out_prefix, cam_name), cam)
    else:
        cam = CAMERAS[args.cam]
        r.set_camera(eye=cam["eye"], center=cam["center"], up=cam["up"], fovy=cam["fovy"])
        for i, frame in enumerate(frames):
            apply_frame(frame)
            for _ in range(5):
                r.step()
            out = os.path.join(args.out_dir, "%s_%04d.png" % (args.out_prefix, i))
            r.save_png(out)
            print("frame", i, "->", out, flush=True)
    print("RENDER DONE", flush=True)


if __name__ == "__main__":
    main()
