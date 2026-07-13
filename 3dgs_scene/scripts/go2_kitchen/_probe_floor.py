"""诊断：把 collider 变到 Genesis 空间，找从任意起点沿 ±x/±y 的空地 runway + 墙位置，
好把 go2 放到开阔中线、朝长轴走。

Genesis 加载 GLB：verts_zup = (x,-z,y)，再 + morph pos=(0,0.92,1.1)。
"""
import argparse

import numpy as np
import trimesh

POS = np.array([0.0, 0.92, 1.1])


def to_gen(v):
    # glTF Y-up (x,y,z) -> Genesis Z-up (x,-z,y) + pos
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1) + POS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", default="/work/assets/rustic_kitchen_collider.glb")
    ap.add_argument("--zband", type=float, nargs=2, default=[0.4, 1.6], help="墙带高度(gen z)")
    ap.add_argument("--corridor", type=float, default=0.5, help="走廊半宽(m)")
    ap.add_argument("--start", type=float, nargs=2, default=[0.0, 0.0])
    args = ap.parse_args()

    scene = trimesh.load(args.glb, force="scene")
    V = np.concatenate([to_gen(np.asarray(g.vertices)) for g in scene.geometry.values()], axis=0)
    print(f"verts={len(V)}  AABB gen: x[{V[:,0].min():.2f},{V[:,0].max():.2f}] "
          f"y[{V[:,1].min():.2f},{V[:,1].max():.2f}] z[{V[:,2].min():.2f},{V[:,2].max():.2f}]")

    # 墙带（竖直结构）
    wall = V[(V[:, 2] > args.zband[0]) & (V[:, 2] < args.zband[1])]
    sx, sy = args.start
    c = args.corridor
    # 沿 x 的走廊（|y-sy|<c）：找 sx 两侧最近墙
    corx = wall[np.abs(wall[:, 1] - sy) < c]
    xr = corx[corx[:, 0] > sx][:, 0]
    xl = corx[corx[:, 0] < sx][:, 0]
    cory = wall[np.abs(wall[:, 0] - sx) < c]
    yf = cory[cory[:, 1] > sy][:, 1]
    yb = cory[cory[:, 1] < sy][:, 1]

    def near(a, ref, sign):
        if len(a) == 0:
            return None
        return (a.min() if sign > 0 else a.max()) - ref

    print(f"start=({sx},{sy}) corridor=±{c}m  墙带 z∈{args.zband}")
    print(f"  +x runway: {near(xr, sx, +1)}  (最近 +x 墙)")
    print(f"  -x runway: {near(xl, sx, -1)}  (最近 -x 墙)")
    print(f"  +y runway: {near(yf, sy, +1)}  (最近 +y 墙)")
    print(f"  -y runway: {near(yb, sy, -1)}  (最近 -y 墙)")


if __name__ == "__main__":
    main()
