"""feature9 F9a — AMD 物理地基 drop-test.

最小 Genesis 刚体物理场景：floor plane(z=0) + go2.urdf + 重力，PD 保持站姿，
step N 帧记录 base z 轨迹，判定「站住 / 坠落 / 穿地 / 飞走」。**不渲染**（纯物理），
用来验证 Genesis 刚体物理在本 AMD 节点能否跑 + 定 GPU vs CPU 后端。

用法（容器内 /work/go2_kitchen）：
    python go2_drop_test.py --backend gpu     # 先试 GPU
    python go2_drop_test.py --backend cpu     # fallback

joint 名 / 站姿复用 go2_kitchen_common（与 examples/locomotion/go2_env 一致）。
"""
import argparse

import numpy as np

import genesis as gs

from go2_kitchen_common import GO2_JOINT_NAMES, GO2_STAND_POSE


def main():
    ap = argparse.ArgumentParser()
    # 用 getattr 取后端，便于试 gpu/cpu/amdgpu/vulkan 而不改码
    ap.add_argument("--backend", type=str, default="gpu")
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--init-z", type=float, default=0.42)
    args = ap.parse_args()

    backend = getattr(gs, args.backend)
    gs.init(backend=backend, precision="32", logging_level="info")

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.02, substeps=2),
        rigid_options=gs.options.RigidOptions(enable_self_collision=False),
        show_viewer=False,
    )
    scene.add_entity(gs.morphs.Plane())
    robot = scene.add_entity(
        gs.morphs.URDF(
            file="urdf/go2/urdf/go2.urdf",
            pos=(0.0, 0.0, args.init_z),
            quat=(1.0, 0.0, 0.0, 0.0),
        ),
    )
    scene.build(n_envs=0)

    motors = [robot.get_joint(n).dof_start for n in GO2_JOINT_NAMES]
    robot.set_dofs_kp([20.0] * 12, motors)
    robot.set_dofs_kv([0.5] * 12, motors)
    target = np.asarray(GO2_STAND_POSE, dtype=np.float32)

    def to_np(x):
        # Genesis GPU (gs.amdgpu) 返回 HIP torch tensor，需先搬回 host
        try:
            return x.detach().cpu().numpy()
        except AttributeError:
            return np.asarray(x)

    zs = []
    for i in range(args.steps):
        robot.control_dofs_position(target, motors)
        scene.step()
        z = float(to_np(robot.get_pos()).reshape(-1)[2])
        zs.append(z)
        if i % 25 == 0:
            print(f"step {i:4d}  base_z={z:.4f}", flush=True)

    zs = np.asarray(zs)
    print("=== F9a drop-test summary ===", flush=True)
    print(f"backend={args.backend} init_z={args.init_z} steps={args.steps}")
    print(f"base_z: start={zs[0]:.4f} min={zs.min():.4f} max={zs.max():.4f} final={zs[-1]:.4f}")
    # go2_env base_height_target=0.3；站住 ≈ final 落在 [0.20,0.45] 且未穿地(min>-0.02)
    stands = (0.20 < zs[-1] < 0.45) and (zs.min() > -0.02)
    print("VERDICT:", "STANDS_OK" if stands else "CHECK (fell / penetrated / flew)", flush=True)


if __name__ == "__main__":
    main()
