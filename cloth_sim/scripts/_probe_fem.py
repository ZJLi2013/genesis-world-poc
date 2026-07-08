import inspect
import genesis as gs

gs.init(backend=gs.cpu, logging_level="error")

# FEM.Cloth material signature
print("=== FEM.Cloth signature ===")
try:
    print(inspect.signature(gs.materials.FEM.Cloth.__init__))
except Exception as e:
    print("sig fail", e)

# Build a tiny scene to get a real FEMEntity and list its control methods
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=0.02),
    coupler_options=gs.options.IPCCouplerOptions(contact_d_hat=0.01, two_way_coupling=True),
    show_viewer=False,
)
scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(coup_type="ipc_only"))
from huggingface_hub import snapshot_download
asset = snapshot_download(repo_type="dataset", repo_id="Genesis-Intelligence/assets",
                          revision="8aa8fcd60500b9f3a36c356080224bdb1be9ee59",
                          allow_patterns="IPC/grid20x20.obj", max_workers=1)
cloth = scene.add_entity(
    morph=gs.morphs.Mesh(file=f"{asset}/IPC/grid20x20.obj", scale=1.0, pos=(0, 0, 0.5)),
    material=gs.materials.FEM.Cloth(E=1e5, nu=0.499, rho=200, thickness=0.001, bending_stiffness=50.0),
)
scene.build(n_envs=1)

meths = [m for m in dir(cloth) if not m.startswith("_")]
KEYS = ("pos", "vert", "fix", "set", "get", "state", "veloc", "control", "actuat", "muscle", "constraint", "target", "find", "closest", "release")
print("=== FEMEntity relevant methods ===")
for m in meths:
    if any(k in m.lower() for k in KEYS):
        print(" ", m)
st = cloth.get_state()
print("=== state attrs ===", [a for a in dir(st) if not a.startswith("_")])
