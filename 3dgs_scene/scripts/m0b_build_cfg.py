"""M0b config builder -- Genesis poses JSON -> vk_gs cams.json + seq.cfg.

Reads genesis_poses.json (from m0b_genesis_poses.py), maps each Genesis (Z-up)
pose into the splat (Y-up) frame centered on the scene AABB, then emits the
vk_gs INRIA preset list + benchmark sequence. Pure stdlib + numpy + gs_bridge.
"""
import argparse
import json
import numpy as np

import gs_bridge as gb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", default="/work/gsm0b/genesis_poses.json")
    ap.add_argument("--cams", default="/work/gsm0b/cams.json")
    ap.add_argument("--seq", default="/work/gsm0b/seq.cfg")
    ap.add_argument("--out-dir", default="/work/gsm0b/out")
    ap.add_argument("--prefix", default="m0b")
    # splat AABB center (from ply_bounds.py on rustic_kitchen_2m.ply)
    ap.add_argument("--center", type=float, nargs=3, default=[-0.93, -0.71, -0.75])
    ap.add_argument("--scale", type=float, default=1.0,
                    help="Genesis metre -> splat units (E2). M0b orbit uses 1.0.")
    ap.add_argument("--fov", type=float, default=60.0)
    ap.add_argument("--pipeline", type=int, default=1)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=200)
    args = ap.parse_args()

    meta = json.load(open(args.poses))
    raw = meta["poses"] if isinstance(meta, dict) else meta

    poses = []
    for p in raw:
        e, l, u = gb.genesis_to_splat(p["pos"], p["lookat"], p["up"],
                                      center=args.center, scale=args.scale)
        poses.append((e, l, u))

    cams = gb.build_cams_json(poses, fov_deg=args.fov)
    with open(args.cams, "w") as f:
        json.dump(cams, f, indent=1)

    seq = gb.build_sequence_cfg(len(cams), args.out_dir, out_prefix=args.prefix,
                                pipeline=args.pipeline, frames=args.frames,
                                warmup=args.warmup)
    with open(args.seq, "w") as f:
        f.write(seq)

    print(f"WROTE {args.cams} ({len(cams)} cams) and {args.seq}")
    print("cam0:", json.dumps(cams[0]))
    print("CFG_OK")


if __name__ == "__main__":
    main()
