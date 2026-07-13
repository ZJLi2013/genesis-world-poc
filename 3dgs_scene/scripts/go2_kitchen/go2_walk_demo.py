"""feature9 F9d — Go2 用训好的 locomotion 策略在 3DGS 厨房里**物理行走**并在线渲染成 mp4。

feature8 的 go2_sensor_demo 是 kinematic 扫掠（假动、无碰撞、会穿墙）。这里换成真物理：
  - 场景 = 厨房 collider（对齐 splat，F9b）+ go2；GPU（gs.amdgpu）刚体物理。
  - 驱动 = F9c 训好的 RL 策略（model_100.pt）逐步推 obs→action→PD 关节控制。
  - 渲染 = 每 env.step 后 go2 真实 FK 位姿经 go2_gsplat_plugin sensor 合成进 splat。
  - 出帧 = 原始 RGB 直接管道进系统 ffmpeg → 单个 mp4（无逐帧 PNG）。

相机默认用 go2_gsplat_plugin 的全景 observer 默认机位（splat 空间）；可用 --cam-*
（splat）或 --cam-*-gen（Genesis 坐标，经 feature3 映射）覆盖。

在 vkgs_build 容器内、/work/locomotion 下（取 logs/go2-walking）跑：
    xvfb-run -a python /work/go2_kitchen/go2_walk_demo.py --gpu 2 \
        --out /work/out/f9_go2/g3_go2_walk.mp4
"""
import argparse
import math
import os
import pickle
import subprocess
import sys
import time

VKGS_BUILD = os.environ.get("VKGS_BUILD", "/work/vk_gaussian_splatting/build")
sys.path.insert(0, VKGS_BUILD)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def ensure_display():
    if sys.platform == "win32" or os.environ.get("DISPLAY"):
        return
    if subprocess.run(["which", "Xvfb"], capture_output=True).returncode != 0:
        return
    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x1024x24", "-ac", "+extension", "GLX"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["DISPLAY"] = ":99"
    time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/work/out/f9_go2/g3_go2_walk.mp4")
    ap.add_argument("--frames", type=int, default=150, help="控制步数（每步 dt=0.02s）")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--res", type=int, nargs=2, default=[1280, 720])
    ap.add_argument("--gpu", type=int, default=2)
    ap.add_argument("--log-dir", default="/work/locomotion/logs/go2-walking")
    ap.add_argument("--ckpt", type=int, default=100)
    ap.add_argument("--collider", default="/work/assets/rustic_kitchen_collider.glb")
    ap.add_argument("--floor", choices=["plane", "collider", "both"], default="collider",
                    help="plane=干净平地(稳); collider=厨房碰撞mesh(遵守几何,但地面偏不平); both=平地+墙")
    ap.add_argument("--ply", default="/work/assets/rustic_kitchen_2m.ply")
    ap.add_argument("--assets", default="/work/assets/go2")
    # 固定速度指令（覆盖 cfg 随机范围）。默认沿用 cfg（前进 0.5）。
    ap.add_argument("--cmd-vx", type=float, default=None)
    ap.add_argument("--cmd-vy", type=float, default=None)
    ap.add_argument("--cmd-vw", type=float, default=None)
    # 相机覆盖（splat 空间）
    ap.add_argument("--cam-eye", type=float, nargs=3, default=None)
    ap.add_argument("--cam-center", type=float, nargs=3, default=None)
    ap.add_argument("--cam-fovy", type=float, default=None)
    # 相机覆盖（Genesis 坐标，经 feature3 映射到 splat；优先于 --cam-eye）
    ap.add_argument("--cam-eye-gen", type=float, nargs=3, default=None)
    ap.add_argument("--cam-center-gen", type=float, nargs=3, default=None)
    ap.add_argument("--cam-up-gen", type=float, nargs=3, default=[0.0, 0.0, 1.0])
    # 跟拍相机：每帧钉到 go2 base(gen) + 偏移，随 go2 前进而后退，看进厨房深处
    ap.add_argument("--cam-follow", action="store_true")
    ap.add_argument("--follow-eye-off", type=float, nargs=3, default=[0.0, -1.0, 0.8],
                    metavar=("DX", "DY", "DZ"), help="gen: 机位相对 base 偏移（后方+抬高）")
    ap.add_argument("--follow-center-off", type=float, nargs=3, default=[0.0, 0.8, 0.1],
                    metavar=("DX", "DY", "DZ"), help="gen: 注视点相对 base 偏移（前方）")
    ap.add_argument("--preview", type=int, default=-1, help=">=0：只跑该步数并存一张 PNG（调机位）")
    # go2 起点 / 朝向（覆盖 cfg base_init_pos/quat）。yaw 绕世界 +Z（度）：
    # 长轴 = Genesis y（feature3 深 6），故 yaw=90/-90 让 body-forward 对上 ±y 沿中线走。
    ap.add_argument("--start-xy", type=float, nargs=2, default=None, metavar=("X", "Y"))
    ap.add_argument("--yaw", type=float, default=None, help="base yaw about world +Z (deg)")
    args = ap.parse_args()

    os.environ.setdefault("HIP_VISIBLE_DEVICES", str(args.gpu))
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(args.gpu))

    import numpy as np
    import torch

    import go2_kitchen_common as gkc

    ensure_display()

    import genesis as gs

    gs.init(backend=gs.gpu, logging_level="info")

    # import AFTER gs.init: the sensor plugin pulls genesis.engine.sensors, which
    # needs gs.qd_float (only set during gs.init).
    from rsl_rl.runners import OnPolicyRunner
    from go2_env_kitchen import Go2KitchenEnv

    with open(os.path.join(args.log_dir, "cfgs.pkl"), "rb") as f:
        env_cfg, obs_cfg, reward_cfg, command_cfg, train_cfg = pickle.load(f)

    reward_cfg["reward_scales"] = {}  # demo 不需要 reward
    # 不在片段中途因摔倒/超时把 go2 瞬移回原点
    env_cfg["termination_if_pitch_greater_than"] = 1e4
    env_cfg["termination_if_roll_greater_than"] = 1e4
    env_cfg["episode_length_s"] = 1e5
    if args.start_xy is not None:
        z0 = env_cfg["base_init_pos"][2]
        env_cfg["base_init_pos"] = [args.start_xy[0], args.start_xy[1], z0]
    if args.yaw is not None:
        r = math.radians(args.yaw)
        env_cfg["base_init_quat"] = [math.cos(r / 2.0), 0.0, 0.0, math.sin(r / 2.0)]
    if args.cmd_vx is not None:
        command_cfg["lin_vel_x_range"] = [args.cmd_vx, args.cmd_vx]
    if args.cmd_vy is not None:
        command_cfg["lin_vel_y_range"] = [args.cmd_vy, args.cmd_vy]
    if args.cmd_vw is not None:
        command_cfg["ang_vel_range"] = [args.cmd_vw, args.cmd_vw]

    cam_kwargs = dict(res=tuple(args.res), gpu=args.gpu, ply=args.ply,
                      assets=args.assets, robot_entity_idx=1)
    if args.cam_eye_gen is not None:
        cam_kwargs["cam_eye"] = tuple(gkc.gen_point_to_splat(args.cam_eye_gen))
        cam_kwargs["cam_up"] = tuple(gkc.gen_vec_to_splat(args.cam_up_gen))
        if args.cam_center_gen is not None:
            cam_kwargs["cam_center"] = tuple(gkc.gen_point_to_splat(args.cam_center_gen))
    else:
        if args.cam_eye is not None:
            cam_kwargs["cam_eye"] = tuple(args.cam_eye)
        if args.cam_center is not None:
            cam_kwargs["cam_center"] = tuple(args.cam_center)
    if args.cam_fovy is not None:
        cam_kwargs["cam_fovy"] = args.cam_fovy
    if args.cam_follow:
        cam_kwargs["cam_follow"] = True
        cam_kwargs["follow_eye_off"] = tuple(args.follow_eye_off)
        cam_kwargs["follow_center_off"] = tuple(args.follow_center_off)
        cam_kwargs["cam_up_gen"] = tuple(args.cam_up_gen)

    env = Go2KitchenEnv(
        num_envs=1, env_cfg=env_cfg, obs_cfg=obs_cfg, reward_cfg=reward_cfg,
        command_cfg=command_cfg, collider_glb=args.collider, floor=args.floor,
        cam_kwargs=cam_kwargs, show_viewer=False,
    )
    print("BUILD OK; splat", env.cam._shared_metadata.renderer.splat_count(),
          "instances", len(env.cam._shared_metadata.instances), flush=True)

    runner = OnPolicyRunner(env, train_cfg, args.log_dir, device=gs.device)
    runner.load(os.path.join(args.log_dir, f"model_{args.ckpt}.pt"))
    policy = runner.get_inference_policy(device=gs.device)

    obs = env.reset()
    if args.cmd_vx is not None or args.cmd_vy is not None or args.cmd_vw is not None:
        env.set_command(command_cfg["lin_vel_x_range"][0],
                        command_cfg["lin_vel_y_range"][0],
                        command_cfg["ang_vel_range"][0])

    def _np(x):
        return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.preview >= 0:
        import imageio.v2 as imageio
        with torch.no_grad():
            for _ in range(max(args.preview, 1)):
                obs, _, _, _ = env.step(policy(obs))
        frame = env.render_rgb()
        imageio.imwrite(args.out, frame)
        print("PREVIEW step", args.preview, "->", args.out, "shape", frame.shape, flush=True)
        return

    w, h = args.res
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", args.out],
        stdin=subprocess.PIPE,
    )
    p0 = _np(env.robot.get_pos()).reshape(-1).copy()
    with torch.no_grad():
        for i in range(args.frames):
            obs, _, _, _ = env.step(policy(obs))
            frame = env.render_rgb()
            ff.stdin.write(frame.tobytes())
            if i % 30 == 0:
                p = _np(env.robot.get_pos()).reshape(-1)
                print(f"frame {i:4d} base=({p[0]:.2f},{p[1]:.2f},{p[2]:.2f}) "
                      f"mean={float(frame.mean()):.1f}", flush=True)
    ff.stdin.close()
    ff.wait()
    pf = _np(env.robot.get_pos()).reshape(-1)
    print(f"G3 DONE frames={args.frames} fps={args.fps} rc={ff.returncode} -> {args.out}", flush=True)
    print(f"base start=({p0[0]:.2f},{p0[1]:.2f},{p0[2]:.2f}) end=({pf[0]:.2f},{pf[1]:.2f},{pf[2]:.2f}) "
          f"dx={pf[0]-p0[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
