"""Render a worldlabs Gaussian-splat scene with Genesis' Nyx path tracer.

Verifies Genesis 1.0 3DGS rendering support (upstream issue #1358, resolved by Nyx).
The splat is a camera-side LightFieldAsset (not a Genesis entity); rendering happens
during scene.step(), frames are pulled via cam.read().rgb.

Usage (on an NVIDIA node with gs-nyx-plugin installed):
    python render_kitchen.py --ply assets/rustic_kitchen_500k.ply --out out/kitchen.png
"""
import argparse
import os

import numpy as np
from PIL import Image

import genesis as gs
import gs_nyx.nyx_py_renderer as npr
import gs_nyx.nyx_py_sdk as nps
from gs_nyx_plugin.nyx_camera_options import NyxCameraOptions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True, help="path to Gaussian-splat PLY")
    ap.add_argument("--out", default="out/kitchen.png")
    ap.add_argument("--res", type=int, nargs=2, default=[1920, 1080])
    ap.add_argument("--spp", type=int, default=64)
    ap.add_argument("--pos", type=float, nargs=3, default=[0.0, -2.5, 1.4])
    ap.add_argument("--lookat", type=float, nargs=3, default=[0.0, 0.0, 1.0])
    ap.add_argument("--fov", type=float, default=60.0)
    # worldlabs is OpenCV (+x left,+y down,+z forward); Genesis is Z-up.
    # Default: same +90 deg about Z as the bundled plant example; override to calibrate.
    ap.add_argument("--quat", type=float, nargs=4, default=[0.0, 0.0, -0.70710678, 0.70710678],
                    help="splat rotation quaternion (x,y,z,w)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    gs.init()
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.01),
        show_viewer=False,
    )

    splat = nps.LightFieldAsset()
    splat.type = nps.ELightFieldType.GaussianField
    splat.uri = os.path.abspath(args.ply)
    splat.rotation = nps.quaternion(*args.quat)

    cam = scene.add_sensor(NyxCameraOptions(
        res=tuple(args.res),
        pos=tuple(args.pos),
        lookat=tuple(args.lookat),
        fov=args.fov,
        spp=args.spp,
        render_mode=npr.ERenderMode.FastPathTracer,
        light_fields=[splat],
    ))

    scene.build(n_envs=1)
    scene.step()

    rgb = cam.read().rgb[0].cpu().numpy()
    Image.fromarray(rgb.astype(np.uint8)).save(args.out)
    print(f"Saved {args.out}  (nonzero pixels: {np.count_nonzero(rgb)}/{rgb.size})")


if __name__ == "__main__":
    main()
