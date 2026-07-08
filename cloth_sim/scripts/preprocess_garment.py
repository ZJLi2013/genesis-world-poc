"""把下载的衣物网格(gltf/glb/obj)归一化成可直接进 Genesis PBD 的小 obj。

流水线(见 docs/cloth_asset.md §3.2 + design/feature8_garment_mesh_quality.md):
  1) 连通性过滤: 真实衣物 gltf 常是多个不连通片(衣身/袖/trims), 各片在 PBD 里独立乱飞→尖刺。
     只保留顶点数最大的 --keep-components 片。
  2) 焊接 + 去退化: merge_vertices + 去重复/零面积面 + 去孤立点。
  3) 居中 + 尺度: 最大边→--size 米(默认 0.4, 人手可抓)。
  4) 抽稀: PBD 粒子=顶点, 压到 --verts(默认 1200)。
     默认 quadric(保形); --uniform 用 pyacvd 均匀重网格(粒子间距均匀, PBD 更稳)。
不做旋转: 朝向交给 50_*/40_* 脚本的 euler=(90,0,0)(Y-up→Z-up)。

用法:
    python scripts/preprocess_garment.py \
        --in "assets/Ripped Shirt_thin/RippedShirt_gltf_thin.gltf" \
        --out meshes/ripped_shirt.obj
    # 若 quadric 仍尖刺, 加 --uniform 换均匀重网格(需 pip install pyacvd pyvista)
"""
import argparse
import os

import numpy as np
import trimesh


def keep_largest_components(m: trimesh.Trimesh, n: int) -> trimesh.Trimesh:
    comps = m.split(only_watertight=False)
    if len(comps) <= 1:
        return m
    comps = sorted(comps, key=lambda c: len(c.vertices), reverse=True)
    kept = comps[:max(1, n)]
    print(f"[comp] {len(comps)} 片 -> 保留最大 {len(kept)} 片 "
          f"(顶点 {[len(c.vertices) for c in kept]})")
    return trimesh.util.concatenate(kept) if len(kept) > 1 else kept[0]


def clean(m: trimesh.Trimesh) -> trimesh.Trimesh:
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())   # 去零面积面
    m.update_faces(m.unique_faces())          # 去重复面
    m.remove_unreferenced_vertices()
    return m


def decimate_quadric(m: trimesh.Trimesh, target_verts: int) -> trimesh.Trimesh:
    if len(m.vertices) <= target_verts:
        return m
    try:
        d = m.simplify_quadric_decimation(face_count=max(4, target_verts * 2))
        if d is not None and len(d.vertices) > 0:
            return d
    except Exception as e:  # noqa: BLE001
        print(f"[warn] quadric 抽稀失败({e})")
    return m


def remesh_uniform(m: trimesh.Trimesh, target_verts: int) -> trimesh.Trimesh:
    """pyacvd 均匀重网格: 边长均匀, PBD 粒子间距一致。需 pyacvd+pyvista。"""
    import pyacvd
    import pyvista as pv
    faces = np.hstack([np.full((len(m.faces), 1), 3), m.faces]).astype(np.int64)
    pvm = pv.PolyData(m.vertices, faces)
    clus = pyacvd.Clustering(pvm)
    # 需要足够细分基网格才能均匀采到 target 个簇
    if pvm.n_points < target_verts * 3:
        clus.subdivide(2)
    clus.cluster(target_verts)
    rm = clus.create_mesh()
    f = rm.faces.reshape(-1, 4)[:, 1:]
    return trimesh.Trimesh(vertices=rm.points, faces=f, process=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=float, default=0.4, help="归一化后最大边(米)")
    p.add_argument("--verts", type=int, default=1200, help="目标顶点数(PBD 粒子数)")
    p.add_argument("--keep-components", type=int, default=1, help="保留最大的 N 个连通片")
    p.add_argument("--uniform", action="store_true", help="用 pyacvd 均匀重网格替代 quadric 抽稀")
    args = p.parse_args()

    m = trimesh.load(args.inp, force="mesh")
    print(f"[in ] verts={len(m.vertices)} faces={len(m.faces)} extents={m.extents}")

    m = keep_largest_components(m, args.keep_components)   # 1) 连通性过滤
    m = clean(m)                                            # 2) 焊接+去退化
    m.apply_translation(-m.bounds.mean(axis=0))             # 3) 居中
    m.apply_scale(args.size / m.extents.max())              #    最大边→size 米
    m = remesh_uniform(m, args.verts) if args.uniform else decimate_quadric(m, args.verts)  # 4) 抽稀/重网格
    m = clean(m)

    ncomp = len(m.split(only_watertight=False))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    m.export(args.out)
    print(f"[out] verts={len(m.vertices)} faces={len(m.faces)} extents={m.extents}")
    print(f"      components={ncomp} watertight={m.is_watertight} winding_ok={m.is_winding_consistent}")
    print(f"      wrote {args.out}")


if __name__ == "__main__":
    main()
