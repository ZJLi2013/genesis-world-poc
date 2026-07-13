"""Convert Unitree Go2 visual COLLADA (.dae) meshes to .glb for vk_gs (feature8).

vk_gs `add_mesh` -> `loadModel` accepts `.obj/.gltf/.glb` (vkgs_pybind.cpp). Go2's
`.dae` are FLAT-SHADED MULTI-MATERIAL models (no texture images): e.g. base.dae has
5 sub-materials — a light-grey/silver top shell, white accents, and near-black body.
An earlier attempt exported `.obj` + one averaged `set_mesh_color`, which collapsed
all 5 materials into a single mid-grey blob (the "no texture / all grey" bug).

Fix: export `.glb`, which preserves every sub-mesh's own baseColor, and load it
WITHOUT `set_mesh_color` so vk_gs renders each material's real color. glTF baseColor
is linear (spec), so no sRGB conversion here.

Runs anywhere with trimesh + pycollada (no GPU).

Usage:
    python go2_dae2glb.py --dae-dir <go2/dae> --out-dir <assets/go2>
    python go2_dae2glb.py --out-dir /work/assets/go2      # dae from genesis assets
"""
import argparse
import glob
import os

import trimesh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dae-dir", default=None, help="dir of Go2 .dae (default: genesis assets go2/dae)")
    ap.add_argument("--out-dir", default="/work/assets/go2", help="output dir for .glb")
    args = ap.parse_args()

    dae_dir = args.dae_dir
    if dae_dir is None:
        import genesis as gs

        dae_dir = os.path.join(gs.utils.get_assets_dir(), "urdf", "go2", "dae")

    dae_files = sorted(glob.glob(os.path.join(dae_dir, "*.dae")))
    if not dae_files:
        raise SystemExit(f"no .dae under {dae_dir}")

    os.makedirs(args.out_dir, exist_ok=True)
    for dae in dae_files:
        base = os.path.splitext(os.path.basename(dae))[0]
        scene = trimesh.load(dae, force="scene")
        out = os.path.join(args.out_dir, base + ".glb")
        scene.export(out)
        n_mat = len(scene.geometry)
        print(f"OK {base:14s} -> {os.path.basename(out)}  ({n_mat} sub-material(s))")

    print(f"wrote {len(dae_files)} glb to {args.out_dir}")


if __name__ == "__main__":
    main()
