"""Quick check: can a Franka grip an IPC FEM.Cloth edge via two_way_soft_constraint
and lift it? (prereq for robot-driven fold under IPC). Based on ipc_robot_grasp_cube.py.
"""
import argparse, os, numpy as np
from huggingface_hub import snapshot_download
import genesis as gs


def to_np(v):
    import torch
    return v.detach().cpu().numpy() if isinstance(v, torch.Tensor) else np.asarray(v)


ap = argparse.ArgumentParser()
ap.add_argument("--render", action="store_true")
ap.add_argument("--out", default="output/feature10/grip")
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)

gs.init(backend=gs.gpu, logging_level="warning")
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=0.01),
    coupler_options=gs.options.IPCCouplerOptions(
        constraint_strength_translation=10.0, constraint_strength_rotation=10.0,
        enable_rigid_rigid_contact=False, enable_rigid_ground_contact=False,
        newton_translation_tolerance=10.0, contact_d_hat=0.004),
    show_viewer=False,
)
scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(coup_type="ipc_only"))

franka = scene.add_entity(
    gs.morphs.MJCF(file="xml/franka_emika_panda/panda_non_overlap.xml"),
    material=gs.materials.Rigid(coup_friction=0.8, coup_type="two_way_soft_constraint",
                                coup_links=("left_finger", "right_finger")),
)
# flat cloth in front of robot; far edge near x=0.62 within reach
cloth = scene.add_entity(
    morph=gs.morphs.Mesh(file=f"{snapshot_download(repo_type='dataset', repo_id='Genesis-Intelligence/assets', revision='8aa8fcd60500b9f3a36c356080224bdb1be9ee59', allow_patterns='IPC/grid20x20.obj', max_workers=1)}/IPC/grid20x20.obj",
                         scale=0.4, pos=(0.45, 0.0, 0.03), euler=(90, 0, 0)),
    material=gs.materials.FEM.Cloth(E=6e4, nu=0.49, rho=200, thickness=0.001,
                                    bending_stiffness=10.0, friction_mu=0.5),
)
cam = scene.add_camera(res=(640, 480), pos=(1.4, 1.0, 0.8), lookat=(0.45, 0, 0.05), fov=45, GUI=False) if args.render else None
scene.build()

motors, fingers = slice(0, 7), slice(7, 9)
ee = franka.get_link("hand")
franka.set_dofs_kp([4500., 4500., 3500., 3500., 2000., 2000., 2000., 500., 500.])
franka.set_dofs_kv([100., 100.], fingers)

frames = []
def snap():
    if cam is not None:
        frames.append(np.asarray(cam.render()[0])[:, :, :3].astype(np.uint8))

def move(pos, grip, n):
    q = franka.inverse_kinematics(link=ee, pos=np.array(pos), quat=np.array([0., 1., 0., 0.]))
    franka.control_dofs_position(q[motors], dofs_idx_local=motors)
    franka.control_dofs_position(grip, dofs_idx_local=fingers)
    for _ in range(n):
        scene.step(); snap()

z_edge = 0.03
P0 = to_np(cloth.get_state().pos).reshape(-1, 3)
xe = P0[:, 0].max()  # far edge x
print(f"[grip] cloth far edge x={xe:.3f} z0max={P0[:,2].max():.3f}")

move([xe, 0.0, 0.25], 0.04, 60)     # above far edge, open
move([xe, 0.0, 0.055], 0.04, 60)    # descend to cloth
move([xe, 0.0, 0.055], 0.0, 40)     # close -> pinch
move([xe, 0.0, 0.35], 0.0, 80)      # lift

Pl = to_np(cloth.get_state().pos).reshape(-1, 3)
print(f"[grip] after lift cloth zmax={Pl[:,2].max():.3f} zmin={Pl[:,2].min():.3f} finite={bool(np.isfinite(Pl).all())}")
print("[grip] GRIP_OK" if Pl[:, 2].max() > 0.15 else "[grip] GRIP_FAIL (cloth not lifted)")

if cam is not None and frames:
    import imageio
    v = os.path.join(args.out, "grip.mp4")
    w = imageio.get_writer(v, fps=30)
    for f in frames: w.append_data(f)
    w.close()
    print("[grip] video", v, len(frames))
print("[grip] DONE")
