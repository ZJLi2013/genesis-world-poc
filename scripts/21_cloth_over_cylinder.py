"""feature2: 布料搭在水平刚性圆柱上 —— bending_compliance 的曲率敏感标定。

单边悬挂的平面布平衡态是「平整竖直」(零曲率→bending 无效)；把布搭在圆柱上则【强制】
产生曲率，bending 刚度才会体现：硬布外鼓(水平展宽大、底部更高)，软布贴合圆柱(更窄、垂得更深)。

用法:
    python scripts/21_cloth_over_cylinder.py --backend amdgpu --bending 1e-4 --out output/feature2/cyl
"""
import argparse
import os

os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {"amdgpu": lambda: gs.amdgpu, "vulkan": lambda: gs.vulkan,
            "cuda": lambda: gs.cuda, "cpu": lambda: gs.cpu}

CLOTH_N = 40
CYL_Z = 0.9
CYL_R = 0.04


def write_grid_obj(path, n, size):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    xs = np.linspace(-size / 2, size / 2, n)
    ys = np.linspace(-size / 2, size / 2, n)
    lines = [f"v {x:.6f} {y:.6f} 0.0" for y in ys for x in xs]
    for j in range(n - 1):
        for i in range(n - 1):
            a, b = j * n + i + 1, j * n + (i + 1) + 1
            c, d = (j + 1) * n + (i + 1) + 1, (j + 1) * n + i + 1
            lines.append(f"f {a} {b} {c}")
            lines.append(f"f {a} {c} {d}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def _save_png(arr, path):
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    try:
        from PIL import Image
        Image.fromarray(arr).save(path)
    except Exception:  # noqa: BLE001
        np.save(path.replace(".png", ".npy"), arr)


def _to_np(t):
    return t.cpu() if hasattr(t, "cpu") else t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    p.add_argument("--bending", type=float, default=1e-4)
    p.add_argument("--stretch", type=float, default=1e-8)
    p.add_argument("--size", type=float, default=0.4)
    p.add_argument("--rho", type=float, default=1.0)
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--render-every", type=int, default=300)
    p.add_argument("--out", default="output/feature2/cyl")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    grid_obj = f"assets/cloth/_grid_{CLOTH_N}_{args.size}.obj"
    write_grid_obj(grid_obj, CLOTH_N, args.size)

    gs.init(backend=BACKENDS[args.backend]())
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=0.01, max_stretch_solver_iterations=8, max_bending_solver_iterations=4
        ),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    # 水平刚性圆柱（轴沿 Y），固定。
    scene.add_entity(
        gs.morphs.Cylinder(radius=CYL_R, height=0.5, pos=(0.0, 0.0, CYL_Z),
                           euler=(90.0, 0.0, 0.0), fixed=True)
    )
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=grid_obj, pos=(0.0, 0.0, CYL_Z + CYL_R + 0.06), euler=(0.0, 0.0, 0.0)),
        material=gs.materials.PBD.Cloth(
            rho=args.rho, stretch_compliance=args.stretch, bending_compliance=args.bending,
            static_friction=0.4, kinetic_friction=0.4,
        ),
    )
    cam = scene.add_camera(res=(640, 480), pos=(0.05, 1.1, CYL_Z + 0.05),
                           lookat=(0.0, 0.0, CYL_Z - 0.15), fov=45, GUI=False)
    scene.build()

    for i in range(args.steps):
        scene.step()
        if i % args.render_every == 0:
            rgb = cam.render(rgb=True)
            arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
            _save_png(arr, os.path.join(args.out, f"frame_{i:05d}.png"))

    pos = np.asarray(_to_np(cloth.get_particles_pos()))
    finite = bool(np.isfinite(pos).all())
    half_width = (pos[:, 0].max() - pos[:, 0].min()) / 2.0  # 硬布外鼓→更大
    bottom_z = pos[:, 2].min()                              # 软布垂得更深→更小
    print(
        f"[cyl-metric] backend={args.backend} stretch={args.stretch:g} bending={args.bending:g} "
        f"finite={finite} half_width={half_width:.4f} bottom_z={bottom_z:.4f}"
    )


if __name__ == "__main__":
    main()
