"""feature2: 布料悬臂垂坠 + compliance 物性标定。

把一块网格布水平悬空，钉住一条边（cantilever），重力使自由边下垂。
自由边的 sag(下垂量) 随 bending/stretch compliance 单调变化 —— 作为 compliance
物性标定的可量化判据。侧视相机渲染 XZ 剖面，便于人工核对垂坠形态。

用法:
    python scripts/20_cloth_drape.py --backend amdgpu --bending 1e-4 --stretch 1e-7 \
        --steps 1200 --out output/feature2/b1e-4
"""
import argparse
import os

os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {
    "amdgpu": lambda: gs.amdgpu,
    "vulkan": lambda: gs.vulkan,
    "cuda": lambda: gs.cuda,
    "cpu": lambda: gs.cpu,
}

CLOTH_N = 36
CLOTH_SIZE = 0.4
CLOTH_Z = 1.0


def write_grid_obj(path: str, n: int, size: float) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    xs = np.linspace(-size / 2, size / 2, n)
    ys = np.linspace(-size / 2, size / 2, n)
    lines = []
    for y in ys:
        for x in xs:
            lines.append(f"v {x:.6f} {y:.6f} 0.0")
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i + 1
            b = j * n + (i + 1) + 1
            c = (j + 1) * n + (i + 1) + 1
            d = (j + 1) * n + i + 1
            lines.append(f"f {a} {b} {c}")
            lines.append(f"f {a} {c} {d}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def _save_png(arr, path: str) -> None:
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    try:
        from PIL import Image

        Image.fromarray(arr).save(path)
    except Exception:  # noqa: BLE001
        np.save(path.replace(".png", ".npy"), arr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    parser.add_argument("--bending", type=float, default=1e-4, help="bending_compliance")
    parser.add_argument("--stretch", type=float, default=1e-7, help="stretch_compliance")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--render-every", type=int, default=200)
    parser.add_argument("--out", default="output/feature2/drape")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    grid_obj = f"assets/cloth/_grid_{CLOTH_N}_{CLOTH_SIZE}.obj"
    write_grid_obj(grid_obj, CLOTH_N, CLOTH_SIZE)

    gs.init(backend=BACKENDS[args.backend]())
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=0.01,
            max_stretch_solver_iterations=8,
            max_bending_solver_iterations=4,
        ),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=grid_obj, pos=(0.0, 0.0, CLOTH_Z), euler=(0.0, 0.0, 0.0)),
        material=gs.materials.PBD.Cloth(
            stretch_compliance=args.stretch,
            bending_compliance=args.bending,
            static_friction=0.3,
            kinetic_friction=0.3,
        ),
    )
    # 侧视相机：沿 -Y 看，呈现 XZ 剖面的垂坠形态。
    cam = scene.add_camera(
        res=(640, 480), pos=(0.1, 1.4, 1.05), lookat=(0.0, 0.0, 0.85), fov=40, GUI=False
    )
    scene.build()

    # 钉住 x 最小那条边（cantilever 固定端）。
    pos0 = np.asarray(_to_np(cloth.get_particles_pos()))
    x = pos0[:, 0]
    spacing = CLOTH_SIZE / (CLOTH_N - 1)
    pin_mask = x <= (x.min() + 0.6 * spacing)
    pin_idx = np.nonzero(pin_mask)[0].astype(np.int32)
    free_mask = x >= (x.max() - 0.6 * spacing)
    free_idx = np.nonzero(free_mask)[0]
    cloth.fix_particles(particles_idx_local=pin_idx)
    print(f"[drape] pinned={pin_idx.size} free_edge={free_idx.size} pin_z0={pos0[pin_idx,2].mean():.4f}")

    for i in range(args.steps):
        scene.step()
        if i % args.render_every == 0:
            rgb = cam.render(rgb=True)
            arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
            _save_png(arr, os.path.join(args.out, f"frame_{i:05d}.png"))

    pos = np.asarray(_to_np(cloth.get_particles_pos()))
    pin_z = pos[pin_idx, 2].mean()
    free_z = pos[free_idx, 2].mean()
    sag = pin_z - free_z
    finite = bool(np.isfinite(pos).all())
    # 自由边的水平回缩（拉伸越软回缩越多）
    pull_in = pos0[free_idx, 0].mean() - pos[free_idx, 0].mean()
    print(
        f"[drape-metric] backend={args.backend} stretch={args.stretch:g} bending={args.bending:g} "
        f"finite={finite} pin_z={pin_z:.4f} free_z={free_z:.4f} sag={sag:.4f} pull_in={pull_in:.4f}"
    )


def _to_np(t):
    return t.cpu() if hasattr(t, "cpu") else t


if __name__ == "__main__":
    main()
