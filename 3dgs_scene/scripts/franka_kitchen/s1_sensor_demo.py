"""S1 demo: Franka moving in the 3DGS kitchen via the in-loop gsplat sensor.

Ephemeral (feature6 S1). Builds one scene (plane + franka on gs.cpu), attaches
a GsplatCameraSensor, then for each interpolated demo qpos: set joints ->
scene.step() -> cam.read() (triggers render) -> save PNG. Proves control
inversion + live pose sourcing + torch tensor output, all in one process.

Run inside the vkgs_build container (has genesis + vkgs), under xvfb-run.
"""
import argparse
import os
import sys

VKGS_BUILD = os.environ.get("VKGS_BUILD", "/work/vk_gaussian_splatting/build")
sys.path.insert(0, VKGS_BUILD)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="/work/vk_gaussian_splatting/build/s1_motion")
    ap.add_argument("--interp-steps", type=int, default=12)
    ap.add_argument("--res", type=int, nargs=2, default=[1280, 720])
    ap.add_argument("--gpu", type=int, default=1)
    ap.add_argument("--backend", choices=["cpu", "gpu"], default="gpu",
                    help="genesis physics backend (default 'gpu' = gs.gpu physics + vk-gs render on the SAME "
                         "card; Gate B verified). 'cpu' is the fallback (physics on CPU, only vk-gs on GPU). "
                         "In gpu mode this script auto-pins HIP_VISIBLE_DEVICES to --gpu; use a compute-healthy "
                         "card (see feature6.2 — GPU1 was wedged 2026-07-13).")
    args = ap.parse_args()

    # gpu mode: pin genesis/torch compute to the same physical card as vk-gs (--gpu).
    # Vulkan enumeration is independent of HIP_VISIBLE_DEVICES, so vkgs still uses physical --gpu.
    if args.backend == "gpu":
        os.environ.setdefault("HIP_VISIBLE_DEVICES", str(args.gpu))

    from franka_fk_dump import DEMO_KEYFRAMES, JOINT_NAMES, ensure_display, interp_keyframes

    ensure_display()
    import genesis as gs

    gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu)
    print("BACKEND", args.backend, "vkgs_gpu", args.gpu,
          "HIP_VISIBLE_DEVICES", os.environ.get("HIP_VISIBLE_DEVICES"), flush=True)
    scene = gs.Scene(show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml", pos=(0.0, 0.0, 0.0)))

    import gs_gsplat_plugin
    from gs_gsplat_plugin import GsplatCameraOptions

    cam = scene.add_sensor(GsplatCameraOptions(
        res=tuple(args.res), gpu=args.gpu, robot_entity_idx=1,
    ))
    scene.build()
    print("BUILD OK; splat", cam._shared_metadata.renderer.splat_count(),
          "instances", len(cam._shared_metadata.instances), flush=True)

    motors = [franka.get_joint(n).dofs_idx_local[0] for n in JOINT_NAMES]
    qpos_rows = interp_keyframes(DEMO_KEYFRAMES, args.interp_steps)
    os.makedirs(args.out_dir, exist_ok=True)
    renderer = cam._shared_metadata.renderer

    for i, qpos in enumerate(qpos_rows):
        franka.set_dofs_position(qpos, motors)
        scene.step()
        rgb = cam.read().rgb          # triggers in-loop render
        if i % 12 == 0:
            print("frame", i, "rgb", tuple(rgb.shape), rgb.dtype, rgb.device,
                  "mean", round(float(rgb.float().mean()), 1), flush=True)
        renderer.save_png(os.path.join(args.out_dir, "s1_%04d.png" % i))
    print("S1 DONE frames", len(qpos_rows), "->", args.out_dir, flush=True)


if __name__ == "__main__":
    main()
