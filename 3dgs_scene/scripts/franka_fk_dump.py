"""Franka forward-kinematics pose dump (Genesis side of the feature5 pipeline).

Loads the MJCF panda, sets one or more joint configurations, and dumps each
link's WORLD pose (pos + wxyz quat) to JSON. Zero-GPU: runs on `gs.cpu`.

Output schema (consumed by franka_render_kitchen.py):
    {"frames": [ {"links": {"<link>": {"pos": [x,y,z], "quat": [w,x,y,z]}}}, ... ]}

- No `--qpos-json`         -> single frame at HOME_QPOS (F1 static).
- `--qpos-json traj.json`  -> one frame per qpos row (F2 motion keyframes).
  traj.json = list of 9-dof rows [j1..j7, finger1, finger2].

Usage (inside a Genesis container, e.g. genesis-amd:latest):
    python franka_fk_dump.py --out /tmp/franka_poses.json
    python franka_fk_dump.py --qpos-json traj.json --out /tmp/franka_traj.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

JOINT_NAMES = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7",
               "finger_joint1", "finger_joint2"]
HOME_QPOS = np.array([0, -0.3, 0, -2.2, 0, 2.0, 0.79, 0.04, 0.04], dtype=np.float32)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mjcf", default="xml/franka_emika_panda/panda.xml",
                    help="MJCF path resolvable by Genesis assets")
    ap.add_argument("--qpos-json", default=None,
                    help="JSON list of 9-dof qpos rows; default = single HOME_QPOS frame")
    ap.add_argument("--out", default="/tmp/franka_poses.json")
    args = ap.parse_args()

    if args.qpos_json:
        with open(args.qpos_json) as f:
            qpos_rows = [np.asarray(r, dtype=np.float32) for r in json.load(f)]
    else:
        qpos_rows = [HOME_QPOS]

    ensure_display()
    import genesis as gs
    gs.init(backend=gs.cpu)

    scene = gs.Scene(show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file=args.mjcf, pos=(0.0, 0.0, 0.0)))
    scene.build()
    motors = [franka.get_joint(n).dofs_idx_local[0] for n in JOINT_NAMES]

    def arr(x, n):
        a = x.cpu().numpy() if hasattr(x, "cpu") else np.asarray(x)
        return a.reshape(-1)[:n].astype(float).tolist()

    frames = []
    for qpos in qpos_rows:
        franka.set_dofs_position(qpos, motors)
        links = {}
        for link in franka.links:
            links[link.name] = dict(pos=arr(link.get_pos(), 3),
                                    quat=arr(link.get_quat(), 4))  # wxyz
        frames.append({"links": links})

    out = {"frames": frames}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print("FKDUMP frames=%d links=%s -> %s"
          % (len(frames), list(frames[0]["links"].keys()), args.out), flush=True)


if __name__ == "__main__":
    main()
