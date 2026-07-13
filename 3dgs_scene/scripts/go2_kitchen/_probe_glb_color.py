"""诊断：dump go2 glb / dae 每个子网格的材质 baseColor，看配色是否在 dae→glb 转换里丢了。"""
import argparse
import glob
import os

import numpy as np
import trimesh


def dump(path):
    print(f"\n=== {os.path.basename(path)} ===")
    scene = trimesh.load(path, force="scene")
    for name, geom in scene.geometry.items():
        mat = getattr(geom, "visual", None)
        info = []
        m = getattr(mat, "material", None)
        if m is not None:
            for attr in ("baseColorFactor", "main_color", "diffuse", "baseColorTexture"):
                v = getattr(m, attr, None)
                if v is not None and not hasattr(v, "size"):
                    info.append(f"{attr}={v}")
                elif isinstance(v, np.ndarray):
                    info.append(f"{attr}={v.tolist()}")
                elif v is not None:
                    info.append(f"{attr}=<{type(v).__name__}>")
        # vertex colors?
        vc = getattr(mat, "vertex_colors", None)
        if vc is not None and len(vc):
            info.append(f"vtxcol[0]={np.asarray(vc)[0].tolist()}")
        print(f"  {name:24s} faces={len(geom.faces):6d}  {' '.join(info)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb-dir", default="/work/assets/go2")
    ap.add_argument("--dae-dir", default=None)
    ap.add_argument("--only", default="base", help="basename filter substring")
    args = ap.parse_args()

    for g in sorted(glob.glob(os.path.join(args.glb_dir, f"*{args.only}*.glb"))):
        dump(g)
    if args.dae_dir:
        for d in sorted(glob.glob(os.path.join(args.dae_dir, f"*{args.only}*.dae"))):
            dump(d)


if __name__ == "__main__":
    main()
