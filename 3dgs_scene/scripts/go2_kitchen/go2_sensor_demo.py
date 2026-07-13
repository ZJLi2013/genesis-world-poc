"""G1 demo: Unitree Go2 traversing the 3DGS kitchen, rendered by the in-loop
go2 gsplat sensor (feature8 G1).

Core value = validate online vk_gs SCENE RENDERING on AMD: a Go2 walks across the
reconstructed kitchen while an OVERALL observer camera frames the whole room, and
every scene.step() the renderer re-composites the live robot pose into the splats.

Design decisions (see docs/features/feature8_go2_integration.md):
  - Motion = KINEMATIC base sweep (we set the base pose along a straight path each
    frame). No physics locomotion / no collision mesh needed for the rendering demo
    (that's a separate G3 milestone; this kitchen ships no collider GLB). Motion
    therefore always "succeeds" and is deterministic.
  - Camera = static OVERALL observer in SPLAT space (cam_eye/center/fovy), pulled
    back to frame the room. Egocentric follow camera is a later G1c refinement.
  - Output = a single .mp4 assembled in-process by piping raw RGB frames straight
    into a system `ffmpeg` subprocess (no per-frame PNG, no python video deps).
    Only the mp4 is produced/pulled. Needs `ffmpeg` on PATH in the container
    (apt-get install -y ffmpeg once). `--preview` writes one PNG via imageio.

Coordinate note (feature3 calibration, see go2_kitchen_common):
    p_splat = R @ p_gen + T,  R: (x,y,z)_gen -> (x, z, -y)_splat
  so Genesis x -> splat horizontal, Genesis z -> splat up, Genesis y -> splat depth.
  A sweep in Genesis x makes Go2 cross the frame left<->right.

Run inside the vkgs_build container (has genesis + vkgs + imageio), under xvfb-run.
GPU1 was wedged 2026-07-13; render on a compute-healthy card (default gpu=2).

    xvfb-run -a python go2_sensor_demo.py --backend cpu --gpu 2 \
        --out /work/out/f8_go2/g1_go2_kitchen.mp4
    # fast camera tuning (one frame -> png), no video:
    xvfb-run -a python go2_sensor_demo.py --preview 24 --cam-fovy 80 \
        --cam-eye 0 0.4 -1.2 --cam-center 0 -0.2 1.5 --out /work/out/f8_go2/preview.png
"""
import argparse
import math
import os
import subprocess
import sys
import time

VKGS_BUILD = os.environ.get("VKGS_BUILD", "/work/vk_gaussian_splatting/build")
sys.path.insert(0, VKGS_BUILD)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def ensure_display():
    """Headless EGL: spin up Xvfb if there is no DISPLAY (Linux only)."""
    if sys.platform == "win32" or os.environ.get("DISPLAY"):
        return
    if subprocess.run(["which", "Xvfb"], capture_output=True).returncode != 0:
        return
    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x1024x24", "-ac", "+extension", "GLX"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["DISPLAY"] = ":99"
    time.sleep(2)


def _yaw_quat(yaw):
    """Genesis wxyz quaternion for a rotation of `yaw` rad about world +Z."""
    return [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/work/out/f8_go2/g1_go2_kitchen.mp4",
                    help="output .mp4 (or .png in --preview mode)")
    ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--fps", type=int, default=18)
    ap.add_argument("--res", type=int, nargs=2, default=[1280, 720])
    ap.add_argument("--gpu", type=int, default=2)
    ap.add_argument("--backend", choices=["cpu", "gpu"], default="cpu",
                    help="genesis physics backend. Base motion is kinematic either way; 'cpu' is the safe "
                         "default (vkgs still renders on --gpu). GPU1 wedged 2026-07-13 -> use a healthy card.")
    ap.add_argument("--assets", default="/work/assets/go2")
    # kinematic base sweep (Genesis world coords). Default: cross the room in x.
    ap.add_argument("--sweep-start", type=float, nargs=3, default=[-1.2, 0.0, 0.42], metavar=("X", "Y", "Z"))
    ap.add_argument("--sweep-end", type=float, nargs=3, default=[1.2, 0.0, 0.42], metavar=("X", "Y", "Z"))
    ap.add_argument("--yaw", type=float, default=0.0, help="Go2 base yaw (rad) about world +Z")
    ap.add_argument("--wiggle", type=float, default=0.18, help="thigh-joint wiggle amplitude (rad); 0 = still")
    # camera overrides (SPLAT space). Empty -> use plugin Options defaults.
    ap.add_argument("--cam-eye", type=float, nargs=3, default=None)
    ap.add_argument("--cam-center", type=float, nargs=3, default=None)
    ap.add_argument("--cam-fovy", type=float, default=None)
    # camera in GENESIS world coords (intuitive; converted to splat via feature3 map).
    # Overrides --cam-eye/--cam-center if given.
    ap.add_argument("--cam-eye-gen", type=float, nargs=3, default=None)
    ap.add_argument("--cam-center-gen", type=float, nargs=3, default=None)
    ap.add_argument("--cam-up-gen", type=float, nargs=3, default=[0.0, 0.0, 1.0])
    ap.add_argument("--preview", type=int, default=-1,
                    help="if >=0, render only this frame index and save a PNG to --out (fast camera tuning)")
    args = ap.parse_args()

    if args.backend == "gpu":
        os.environ.setdefault("HIP_VISIBLE_DEVICES", str(args.gpu))

    import numpy as np

    import go2_kitchen_common as gkc

    ensure_display()

    import genesis as gs

    gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu)
    print("BACKEND", args.backend, "vkgs_gpu", args.gpu,
          "HIP_VISIBLE_DEVICES", os.environ.get("HIP_VISIBLE_DEVICES"), flush=True)

    scene = gs.Scene(show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    go2 = scene.add_entity(gs.morphs.URDF(file="urdf/go2/urdf/go2.urdf", pos=tuple(args.sweep_start)))

    import go2_gsplat_plugin
    from go2_gsplat_plugin import Go2GsplatCameraOptions

    cam_kw = dict(res=tuple(args.res), gpu=args.gpu, robot_entity_idx=1, assets=args.assets)
    if args.cam_eye is not None:
        cam_kw["cam_eye"] = tuple(args.cam_eye)
    if args.cam_center is not None:
        cam_kw["cam_center"] = tuple(args.cam_center)
    if args.cam_fovy is not None:
        cam_kw["cam_fovy"] = args.cam_fovy

    cam = scene.add_sensor(Go2GsplatCameraOptions(**cam_kw))
    scene.build()
    print("BUILD OK; splat", cam._shared_metadata.renderer.splat_count(),
          "instances", len(cam._shared_metadata.instances), flush=True)

    motors = [go2.get_joint(n).dofs_idx_local[0] for n in gkc.GO2_JOINT_NAMES]
    stand = list(gkc.GO2_STAND_POSE)
    thigh_idx = [1, 4, 7, 10]  # *_thigh_joint positions within GO2_JOINT_NAMES
    quat = _yaw_quat(args.yaw)
    start = np.asarray(args.sweep_start, float)
    end = np.asarray(args.sweep_end, float)
    n = max(args.frames - 1, 1)

    def step_frame(i):
        """Set kinematic base pose + legs for frame i, step, return rgb (H,W,3) uint8 np."""
        t = i / n
        pos = (1.0 - t) * start + t * end
        q = list(stand)
        off = args.wiggle * math.sin(2.0 * math.pi * t)
        for j in thigh_idx:
            q[j] += off
        go2.set_pos(pos.tolist())
        go2.set_quat(quat)
        go2.set_dofs_position(q, motors)
        scene.step()
        rgb = cam.read().rgb  # (B,H,W,3) or (H,W,3) uint8 torch
        arr = rgb.detach().cpu().numpy()
        if arr.ndim == 4:
            arr = arr[0]
        return np.ascontiguousarray(arr[..., :3].astype(np.uint8))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.preview >= 0:
        import imageio.v2 as imageio
        frame = step_frame(args.preview)
        imageio.imwrite(args.out, frame)
        print("PREVIEW frame", args.preview, "->", args.out, "shape", frame.shape, flush=True)
        return

    # Pipe raw RGB frames straight into ffmpeg (no temp PNGs, no imageio-ffmpeg download).
    w, h = args.res
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", args.out],
        stdin=subprocess.PIPE,
    )
    for i in range(args.frames):
        frame = step_frame(i)
        ff.stdin.write(frame.tobytes())
        if i % 12 == 0:
            print("frame", i, "shape", frame.shape, "mean", round(float(frame.mean()), 1), flush=True)
    ff.stdin.close()
    ff.wait()
    print("G1 DONE frames", args.frames, "fps", args.fps, "rc", ff.returncode, "->", args.out, flush=True)


if __name__ == "__main__":
    main()
