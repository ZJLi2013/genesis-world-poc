"""feature1 Exp 1.2: 最小布料 smoke。

程序生成一块网格布，重力下落到地面，PBD 求解；离屏相机渲染若干帧存 PNG，
验证 RDNA4 上 step 稳定 + GPU 渲染生效。不依赖任何外部资产（资产导入留 feature2）。

用法:
    python scripts/10_cloth_smoke.py --backend amdgpu --steps 1000 --out output/smoke
"""
import argparse
import os

# RDNA4 headless：镜像把 PYOPENGL_PLATFORM 预设为 glx（无显示会崩），必须在 import genesis
# 之前【强制】覆盖为 egl（不能用 setdefault，否则保留镜像的 glx）。
os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import genesis as gs

BACKENDS = {
    "amdgpu": lambda: gs.amdgpu,
    "vulkan": lambda: gs.vulkan,
    "cuda": lambda: gs.cuda,
    "cpu": lambda: gs.cpu,
}


def write_grid_obj(path: str, n: int = 40, size: float = 0.5) -> None:
    """生成 n×n 平面网格布的 OBJ（位于 z=0 平面，后续整体抬升下落）。"""
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="amdgpu", choices=list(BACKENDS))
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--out", default="output/smoke")
    parser.add_argument("--render-every", type=int, default=100)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    grid_obj = "assets/cloth/_grid_autogen.obj"
    write_grid_obj(grid_obj)

    gs.init(backend=BACKENDS[args.backend]())

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=4e-3, substeps=10),
        pbd_options=gs.options.PBDOptions(
            particle_size=0.01,
            max_stretch_solver_iterations=8,
            max_bending_solver_iterations=2,
        ),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    cloth = scene.add_entity(
        gs.morphs.Mesh(file=grid_obj, pos=(0.0, 0.0, 0.5), euler=(0.0, 0.0, 0.0)),
        # Genesis 1.1.1 compliance 语义：compliance = 1/刚度，越小越硬。
        material=gs.materials.PBD.Cloth(
            stretch_compliance=1e-7,   # 抗拉伸（硬）
            bending_compliance=1e-4,   # 易弯曲垂坠
            static_friction=0.3,
            kinetic_friction=0.3,
        ),
    )
    cam = scene.add_camera(
        res=(640, 480), pos=(0.9, 0.9, 0.7), lookat=(0.0, 0.0, 0.2), fov=40, GUI=False
    )
    scene.build()

    for i in range(args.steps):
        scene.step()
        if i % args.render_every == 0:
            rgb = cam.render(rgb=True)
            arr = rgb[0] if isinstance(rgb, (tuple, list)) else rgb
            _save_png(arr, os.path.join(args.out, f"frame_{i:05d}.png"))

    # 末帧 + 简单有限性检查（PBD2DEntity 的状态读取 API 因版本而异，逐一尝试）
    arr = _read_particles(cloth)
    if arr is not None:
        print(
            f"[smoke] cloth particles shape={arr.shape} finite={np.isfinite(arr).all()} "
            f"z_min={arr[..., 2].min():.4f} z_max={arr[..., 2].max():.4f}"
        )
    else:
        print(
            f"[smoke] particle read failed; methods="
            f"{[a for a in dir(cloth) if 'pos' in a.lower() or 'particle' in a.lower() or 'state' in a.lower()]}"
        )
    print(f"[smoke] done. steps={args.steps}, frames in {args.out}")


def _read_particles(entity):
    for name in ("get_state", "get_particles", "get_pos", "get_particles_pos"):
        fn = getattr(entity, name, None)
        if fn is None:
            continue
        try:
            out = fn()
        except Exception:  # noqa: BLE001
            continue
        cand = getattr(out, "pos", out)
        try:
            return np.asarray(cand.cpu() if hasattr(cand, "cpu") else cand)
        except Exception:  # noqa: BLE001
            continue
    return None


def _save_png(arr, path: str) -> None:
    arr = np.asarray(arr)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    try:
        from PIL import Image

        Image.fromarray(arr).save(path)
    except Exception:
        np.save(path.replace(".png", ".npy"), arr)


if __name__ == "__main__":
    main()
