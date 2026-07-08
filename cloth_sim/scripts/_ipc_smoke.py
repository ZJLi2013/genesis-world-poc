"""Exp 10.0 smoke: Genesis IPC coupler + FEM.Cloth on NVIDIA GPU.
Minimal: plane(ipc_only) + FEM NeoHookeanShell cloth falling, step N, check finite.
"""
import argparse
import numpy as np
from huggingface_hub import snapshot_download
import genesis as gs

p = argparse.ArgumentParser()
p.add_argument("--backend", default="gpu", choices=["gpu", "cpu"])
p.add_argument("--steps", type=int, default=30)
args = p.parse_args()

gs.init(backend=gs.gpu if args.backend == "gpu" else gs.cpu, logging_level="warning")

scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=0.02),
    coupler_options=gs.options.IPCCouplerOptions(contact_d_hat=0.01, two_way_coupling=True),
    show_viewer=False,
)

# plane must be ipc_only under IPC coupler (1.2.1)
scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(coup_type="ipc_only"))

asset = snapshot_download(
    repo_type="dataset", repo_id="Genesis-Intelligence/assets",
    revision="8aa8fcd60500b9f3a36c356080224bdb1be9ee59",
    allow_patterns="IPC/grid20x20.obj", max_workers=1,
)
cloth = scene.add_entity(
    morph=gs.morphs.Mesh(file=f"{asset}/IPC/grid20x20.obj", scale=1.5, pos=(0.0, 0.0, 1.0), euler=(120, -30, 0)),
    material=gs.materials.FEM.Cloth(E=1e5, nu=0.499, rho=200, thickness=0.001, bending_stiffness=50.0),
)

scene.build(n_envs=1)

import time
t0 = time.time()
for i in range(args.steps):
    scene.step()
dt_ms = (time.time() - t0) / args.steps * 1000

def _to_np(v):
    try:
        import torch
        if isinstance(v, torch.Tensor):
            return v.detach().cpu().numpy()
    except Exception:
        pass
    return np.asarray(v)

# read cloth vertex state -> finite check
st = cloth.get_state()
pos = None
for attr in ("pos", "vertices", "x", "verts"):
    if hasattr(st, attr):
        pos = _to_np(getattr(st, attr))
        break
if pos is None:
    print("[f10.0] stepped OK but could not fetch cloth state attr; dir:", [a for a in dir(st) if not a.startswith("_")][:20])
else:
    pos = pos.reshape(-1, 3)
    finite = bool(np.isfinite(pos).all())
    zmin, zmax = float(pos[:, 2].min()), float(pos[:, 2].max())
    print(f"[f10.0] backend={args.backend} steps={args.steps} finite={finite} "
          f"nverts={pos.shape[0]} z=[{zmin:.3f},{zmax:.3f}] step_ms={dt_ms:.1f}")
print("[f10.0] DONE")
