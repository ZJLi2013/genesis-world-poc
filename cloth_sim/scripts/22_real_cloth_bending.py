"""feature2.1: 真实 cloth.obj + 桌沿悬臂弯曲标定。

用 Genesis 自带 `meshes/cloth.obj`，一半压在固定桌面上(clamped)，另一半悬出桌沿。
悬出段必须在桌沿处弯曲 → bending_compliance 才有判别力（平整悬挂时曲率=0，bending 无效，见 part1-4-exp）。
按 part1-4-exp 的 solver 数学：bending 需推到软区(compliance ≳ ~1e-3)才生效。

用法:
    python scripts/22_real_cloth_bending.py --backend amdgpu --bending 1e-2 --out output/feature2_1/b1e-2
"""
import argparse
import os

os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {"amdgpu": lambda: gs.amdgpu, "vulkan": lambda: gs.vulkan,
            "cuda": lambda: gs.cuda, "cpu": lambda: gs.cpu}

# 桌面 top 高度与桌沿 x 坐标
TABLE_TOP = 0.80
EDGE_X = 0.10
CLOTH_Z = TABLE_TOP + 0.01


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
    p.add_argument("--bending", type=float, default=1e-2)
    p.add_argument("--stretch", type=float, default=1e-7)
    p.add_argument("--scale", type=float, default=0.4, help="cloth.obj 缩放(基准~1m)")
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--render-every", type=int, default=500)
    p.add_argument("--out", default="output/feature2_1/drape")
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
    # 固定桌面：top 在 TABLE_TOP，桌沿在 x=EDGE_X。
    scene.add_entity(
        gs.morphs.Box(size=(0.4, 0.4, TABLE_TOP), pos=(EDGE_X - 0.2, 0.0, TABLE_TOP / 2), fixed=True)
    )
    # 真实布料：中心放在桌沿外侧，使一半在桌上、一半悬出。
    cloth = scene.add_entity(
        gs.morphs.Mesh(file="meshes/cloth.obj", scale=args.scale,
                       pos=(EDGE_X, 0.0, CLOTH_Z), euler=(0.0, 0.0, 0.0)),
        material=gs.materials.PBD.Cloth(
            stretch_compliance=args.stretch, bending_compliance=args.bending,
            static_friction=0.5, kinetic_friction=0.5,
        ),
    )
    cam = scene.add_camera(res=(640, 480), pos=(EDGE_X, 1.1, TABLE_TOP + 0.12),
                           lookat=(EDGE_X + 0.12, 0.0, TABLE_TOP - 0.12), fov=45, GUI=False)
    scene.build()

    # clamp：钉住所有落在桌面上的粒子(x <= EDGE_X)。
    pos0 = np.asarray(_to_np(cloth.get_particles_pos()))
    on_table = np.nonzero(pos0[:, 0] <= EDGE_X)[0].astype(np.int32)
    free = np.nonzero(pos0[:, 0] > EDGE_X)[0]
    cloth.fix_particles(particles_idx_local=on_table)
    print(f"[f21] n={pos0.shape[0]} clamped={on_table.size} free={free.size} "
          f"x_range=[{pos0[:,0].min():.3f},{pos0[:,0].max():.3f}]")

    for i in range(args.steps):
        scene.step()
        if i % args.render_every == 0:
            rgb = cam.render(rgb=True)
            arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
            _save_png(arr, os.path.join(args.out, f"frame_{i:05d}.png"))

    pos = np.asarray(_to_np(cloth.get_particles_pos()))
    finite = bool(np.isfinite(pos).all())
    # 悬出段最尖端(x 最大那一撮)的下垂量
    tip_sel = free[np.argsort(pos0[free, 0])[-30:]]
    tip_z = pos[tip_sel, 2].mean()
    droop = CLOTH_Z - tip_z              # bending 越软→越大
    free_z_min = pos[free, 2].min()
    print(
        f"[f21-metric] backend={args.backend} stretch={args.stretch:g} bending={args.bending:g} "
        f"finite={finite} tip_z={tip_z:.4f} droop={droop:.4f} free_z_min={free_z_min:.4f}"
    )


if __name__ == "__main__":
    main()
