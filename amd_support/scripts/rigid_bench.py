"""F3 独立 rigid benchmark（抽自上游 tests/test_rigid_benchmarks.py，去掉 pytest/conftest）。

用法（容器内）：python rigid_bench.py <name> <n_envs>
  name ∈ go2 anymal_zero anymal_uniform anymal_random franka franka_random franka_free
         box_pyramid_5 g1_fall double_smplx shadow_hand_cubes dex_hand
近期 genesis 上游 get_rigid_solver_options/get_file_morph_options 均走「默认 options」分支 → 此处直接用默认。
输出末行：BENCH_RESULT <json>。
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

import genesis as gs


STEP_DT = 0.01
DURATION_WARMUP = 45.0
DURATION_RECORD = 15.0

HF_ASSETS_REVISION = "990a727788f11e34ad006c69bf769303b20cb11c"


class SceneMeta:
    def __init__(self, compile_time, step_dt=STEP_DT,
                 duration_warmup=DURATION_WARMUP, duration_record=DURATION_RECORD):
        self.compile_time = compile_time
        self.step_dt = step_dt
        self.duration_warmup = duration_warmup
        self.duration_record = duration_record


def get_hf_dataset(pattern, repo_name="assets"):
    from huggingface_hub import snapshot_download
    return snapshot_download(
        repo_type="dataset",
        repo_id=f"Genesis-Intelligence/{repo_name}",
        revision=HF_ASSETS_REVISION,
        allow_patterns=pattern,
        max_workers=1,
    )


# --- factories (options helpers collapse to identity on recent genesis) ---

def make_go2(n_envs, solver=None, gjk=None, **sk):
    scene = gs.Scene(
        rigid_options=gs.options.RigidOptions(
            dt=STEP_DT,
            **({"constraint_solver": solver} if solver is not None else {}),
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    scene.add_entity(gs.morphs.Plane())
    robot = scene.add_entity(gs.morphs.URDF(file="urdf/go2/urdf/go2.urdf"), vis_mode="collision")
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    ctrl_pos = torch.tensor([0.0, 0.8, -1.5, 0.0, 0.8, -1.5, 0.0, 1.0, -1.5, 0.0, 1.0, -1.5],
                            dtype=gs.tc_float, device=gs.device)
    robot.control_dofs_position(ctrl_pos, dofs_idx_local=slice(6, None))
    init_qpos = torch.tensor(
        [[0.0, 0.0, 0.42, 1.0, 0.0, 0.0, 0.0, 0.0, 0.8, -1.5, 0.0, 0.8, -1.5, 0.0, 1.0, -1.5, 0.0, 1.0, -1.5]],
        dtype=gs.tc_float, device=gs.device).repeat((scene.n_envs, 1))
    lo, hi = robot.get_dofs_limit()
    init_qpos[:, 7:] = lo[6:] + (hi[6:] - lo[6:]) * torch.as_tensor(
        np.random.rand(scene.n_envs, robot.n_dofs - 6), dtype=gs.tc_float, device=gs.device)
    robot.set_qpos(init_qpos)
    return scene, (lambda: scene.step()), SceneMeta(compile_time)


def make_anymal(n_envs, solver=None, gjk=None, control=None, **sk):
    scene = gs.Scene(
        rigid_options=gs.options.RigidOptions(
            dt=STEP_DT,
            **({"constraint_solver": solver} if solver is not None else {}),
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    scene.add_entity(gs.morphs.Plane())
    robot = scene.add_entity(gs.morphs.URDF(file="urdf/anymal_c/urdf/anymal_c.urdf", pos=(0, 0, 0.8)))
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    motors = slice(6, None)
    robot.set_dofs_kp(1000.0, motors)
    robot.control_dofs_position(0.0, motors)
    if control == "uniform":
        rand_shape = (12,)
    elif control == "per_env":
        rand_shape = (n_envs, 12)
    else:
        rand_shape = None

    def step():
        if rand_shape is not None:
            robot.control_dofs_position(np.random.rand(*rand_shape) * 0.1 - 0.05, motors)
        scene.step()
    return scene, step, SceneMeta(compile_time)


def make_franka(n_envs, solver=None, gjk=None, is_collision_free=False, is_randomized=False, **sk):
    scene = gs.Scene(
        rigid_options=gs.options.RigidOptions(
            dt=STEP_DT, enable_neutral_collision=True,
            **({"constraint_solver": solver} if solver is not None else {}),
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    qpos0 = torch.tensor([0, 0, 0, -1.0, 0, 1.0, 0, 0.02, 0.02], dtype=gs.tc_float, device=gs.device)
    if n_envs > 0:
        qpos0 = torch.tile(qpos0, (n_envs, 1))
    if is_collision_free:
        franka.set_qpos(qpos0)
        franka.control_dofs_position(qpos0)
    if n_envs > 0 and is_randomized:
        vel0 = 0.2 * np.clip(np.random.randn(n_envs, franka.n_dofs), -1.0, 1.0)
        vel0[:, [link.dof_start for link in franka.links
                 if not link.name.startswith("link") and link.n_dofs]] = 0.0
    else:
        vel0 = torch.zeros((*((n_envs,) if n_envs > 0 else ()), franka.n_dofs),
                           dtype=gs.tc_float, device=gs.device)
    franka.set_dofs_velocity(vel0)
    state_rigid_0 = scene.rigid_solver.get_state()
    if n_envs > 0:
        n_reset = max(int(0.02 * n_envs), 1)
        reset_idx = torch.as_tensor(np.random.permutation(n_envs)[:n_reset], dtype=gs.tc_int, device=gs.device)
        reset_mask = torch.isin(scene._envs_idx, reset_idx)
    else:
        reset_mask = None
    stiff = franka.get_dofs_stiffness()
    damp = franka.get_dofs_damping()
    base_pos0 = franka.get_pos(reset_mask)
    base_quat0 = franka.get_quat(reset_mask)

    def step():
        scene.step()
        scene.rigid_solver.set_state(0, state_rigid_0, envs_idx=reset_mask, partial=True)
        franka.control_dofs_position(qpos0)
        franka.set_dofs_stiffness(stiff)
        franka.set_dofs_damping(damp)
        franka.set_dofs_velocity(vel0, envs_idx=reset_mask, skip_forward=True)
        franka.set_qpos(qpos0, envs_idx=reset_mask, zero_velocity=False, skip_forward=True)
        franka.set_pos(base_pos0, envs_idx=reset_mask, skip_forward=True)
        franka.set_quat(base_quat0, envs_idx=reset_mask, relative=False, skip_forward=True)
    plain_step = (lambda: scene.step())
    return scene, (step if is_randomized else plain_step), SceneMeta(compile_time)


def make_box_pyramid(n_envs, solver=None, gjk=None, n_cubes=5, **sk):
    scene = gs.Scene(
        rigid_options=gs.options.RigidOptions(
            dt=STEP_DT, tolerance=1e-5,
            **({"constraint_solver": solver} if solver is not None else {}),
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    scene.add_entity(gs.morphs.Plane())
    box_size = 0.25
    spacing = (1.0 - 1e-3) * box_size
    offset = (-0.5, 1.0, 0.0) + 0.5 * np.array([box_size, box_size, box_size])
    for i in range(n_cubes):
        for j in range(n_cubes - i):
            scene.add_entity(gs.morphs.Box(size=[box_size] * 3,
                             pos=offset + spacing * np.array([i + 0.5 * j, 0.0, j])))
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    if n_envs > 0:
        for box in scene.entities[1:]:
            box.set_dofs_velocity(0.04 * np.random.rand(n_envs, 6))
    return scene, (lambda: scene.step()), SceneMeta(compile_time)


def make_g1_fall(n_envs, solver=None, gjk=None, **sk):
    step_dt = 0.005
    scene = gs.Scene(
        rigid_options=gs.options.RigidOptions(
            dt=step_dt, iterations=10, tolerance=1e-5, ls_iterations=20,
            **({"constraint_solver": solver} if solver is not None else {}),
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    scene.add_entity(gs.morphs.Plane())
    asset_path = get_hf_dataset(pattern="unitree_g1/*")
    robot = scene.add_entity(
        gs.morphs.MJCF(file=f"{asset_path}/unitree_g1/g1_29dof_rev_1_0.xml", pos=(0, 0, 1.0)),
        vis_mode="collision")
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    init_qpos = torch.zeros((robot.n_qs,), dtype=gs.tc_float, device=gs.device)
    init_qpos[2] = 1.0
    init_qpos[3] = 1.0
    robot.set_qpos(init_qpos)
    forces = torch.zeros((n_envs, robot.n_dofs), dtype=gs.tc_float, device=gs.device)

    def step():
        forces.uniform_(-50.0, 50.0)
        robot.control_dofs_force(forces)
        scene.step()
    return scene, step, SceneMeta(compile_time, step_dt=step_dt, duration_warmup=20.0, duration_record=5.0)


def make_dex_hand(n_envs, solver=None, gjk=None, **sk):
    shadow_hand_path = Path(get_hf_dataset(pattern="shadow_hand/*"))
    dex_path = Path(get_hf_dataset(pattern="dex/*"))
    WRIST_STIFFNESS, FINGER_FORCE, DRILL_STIFFNESS = 20, 0.6, 20
    STEP_DT_ = 1 / 16
    JOINT_NAMES = [*("FFJ4", "FFJ3", "FFJ2", "FFJ1"), *("MFJ4", "MFJ3", "MFJ2", "MFJ1"),
                   *("RFJ4", "RFJ3", "RFJ2", "RFJ1"), *("LFJ5", "LFJ4", "LFJ3", "LFJ2", "LFJ1"),
                   *("THJ5", "THJ4", "THJ3", "THJ2", "THJ1")]
    LEFT_DOFS = [0.34907, 0.24929, 0.54424, 0.65614, 0.21329, 0.08060, 0.19969, 0.66944,
                 1.57080, 0.21846, 0.53605, 0.44963, 0.38350, 0.02379, 0.41705, 0.54773, 0.61160,
                 0.36664, 0.44036, 0.20944, 0.34497, 0.15896]
    RIGHT_DOFS = [0.34907, 0.23328, 0.57399, 0.70467, 0.00000, 0.34907, 0.51778, 0.65078,
                  1.48947, 0.33727, 0.55919, 0.56268, 0.54360, -0.08460, 0.48588, 0.66095, 0.73317,
                  0.13239, 0.45613, 0.20944, 0.19625, 0.00750]
    hand_configs = [
        dict(pos=(0.19227, -0.00058, 1.31227), quat=(-0.45215, -0.31265, 0.76087, 0.34480),
             dofs=LEFT_DOFS, urdf="shadow_hand_left_woarm.urdf"),
        dict(pos=(0.16257, 0.24658, 1.28047), quat=(0.74525, 0.46466, -0.45186, -0.15660),
             dofs=RIGHT_DOFS, urdf="shadow_hand_right_woarm.urdf"),
    ]
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=STEP_DT_, substeps=25),
        rigid_options=gs.options.RigidOptions(
            max_collision_pairs=200,
            **({"use_gjk_collision": gjk} if gjk is not None else {}),
        ),
        **{"show_viewer": False, "show_FPS": False, **sk},
    )
    hands = []
    for cfg in hand_configs:
        urdf_path = str(shadow_hand_path / "shadow_hand" / cfg["urdf"])
        hands.append(scene.add_entity(gs.morphs.URDF(file=urdf_path, pos=cfg["pos"], quat=cfg["quat"])))
    scene.add_entity(gs.morphs.Mesh(file=str(dex_path / "dex" / "table.glb"),
                     pos=(0.1, 0.0, 0.485403), euler=(0, 0, 90), fixed=True))
    drill = scene.add_entity(gs.morphs.Mesh(file=str(dex_path / "dex" / "drill_1.glb"),
                             pos=(0.15, 0.1, 0.87), euler=(90, 0, 225)))
    t0 = time.time()
    scene.build(n_envs=n_envs)
    compile_time = time.time() - t0
    for hand, default_dof in zip(hands, (LEFT_DOFS, RIGHT_DOFS)):
        kp = [WRIST_STIFFNESS] * 6 + [40.0] * (hand.n_dofs - 6)
        hand.set_dofs_kp(kp)
        hand.set_dofs_kv(2.0 * np.sqrt(kp))
        hand.set_dofs_position(default_dof,
            dofs_idx_local=[hand.get_joint(n).dofs_idx_local[0] for n in JOINT_NAMES])
        hand.control_dofs_position(torch.clamp(hand.get_dofs_position(), *hand.get_dofs_limit()))
    finger_dofs = {hand: slice(6, hand.n_dofs) for hand in hands}
    random_forces = {hand: torch.zeros((n_envs, hand.n_dofs - 6), dtype=gs.tc_float, device=gs.device)
                     for hand in hands}
    base_xy = {hand: hand.get_dofs_position()[:, :2] for hand in hands}
    drill.set_dofs_kp(DRILL_STIFFNESS, dofs_idx_local=[0, 1])
    drill.set_dofs_kv(2.0 * math.sqrt(DRILL_STIFFNESS), dofs_idx_local=[0, 1])
    drill_xy = drill.get_dofs_position()[:, :2]
    for hand in hands:
        hand.control_dofs_position(base_xy[hand], dofs_idx_local=[0, 1])
    drill.control_dofs_position(drill_xy, dofs_idx_local=[0, 1])

    def step():
        for hand in hands:
            random_forces[hand].uniform_(-FINGER_FORCE, FINGER_FORCE)
            hand.control_dofs_force(random_forces[hand], dofs_idx_local=finger_dofs[hand])
        scene.step()
    return scene, step, SceneMeta(compile_time, step_dt=STEP_DT_, duration_warmup=20.0, duration_record=5.0)


def run_benchmark(step_fn, *, n_envs, meta):
    import quadrants as qd
    qd.sync()
    step_fn()
    qd.sync()
    num_steps = 0
    is_recording = False
    time_start = time.time()
    while True:
        step_fn()
        elapsed = time.time() - time_start
        if is_recording:
            num_steps += 1
            if elapsed > meta.duration_record:
                qd.sync()
                elapsed = time.time() - time_start
                break
        elif elapsed > meta.duration_warmup:
            qd.sync()
            time_start = time.time()
            is_recording = True
    runtime_fps = int(num_steps * max(n_envs, 1) / elapsed)
    return dict(compile_time=round(meta.compile_time, 2), runtime_fps=runtime_fps,
                realtime_factor=round(runtime_fps * meta.step_dt, 2))


REGISTRY = {
    "go2": (make_go2, {}, 4096),
    "anymal_zero": (make_anymal, {"control": None}, 30000),
    "anymal_uniform": (make_anymal, {"control": "uniform"}, 30000),
    "anymal_random": (make_anymal, {"control": "per_env"}, 30000),
    "franka": (make_franka, {}, 30000),
    "franka_random": (make_franka, {"is_randomized": True}, 30000),
    "franka_free": (make_franka, {"is_collision_free": True}, 30000),
    "box_pyramid_5": (make_box_pyramid, {"n_cubes": 5}, 4096),
    "g1_fall": (make_g1_fall, {"solver": None}, 4096),
    "dex_hand": (make_dex_hand, {}, 4096),
}


def main():
    name = sys.argv[1]
    n_envs = int(sys.argv[2]) if len(sys.argv) > 2 else REGISTRY[name][2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "bench"   # "bench" | "func"
    factory, kwargs, _ = REGISTRY[name]
    gs.init(backend=gs.gpu, logging_level="warning")
    print(f"BENCH_START name={name} n_envs={n_envs} mode={mode} backend={gs.backend} "
          f"device={torch.cuda.get_device_name(0)}", flush=True)
    _, step_fn, meta = factory(n_envs, **kwargs)
    print("BUILT compile_time=%.2fs" % meta.compile_time, flush=True)
    if mode == "func":
        # functional-correctness only: build + a few steps, no timed warmup/record
        import quadrants as qd
        for _ in range(10):
            step_fn()
        qd.sync()
        print("FUNC_RESULT " + json.dumps(dict(name=name, n_envs=n_envs, status="OK",
              compile_time=round(meta.compile_time, 2), backend=str(gs.backend))), flush=True)
        return
    res = run_benchmark(step_fn, n_envs=n_envs, meta=meta)
    res.update(name=name, n_envs=n_envs, backend=str(gs.backend))
    print("BENCH_RESULT " + json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
