"""feature9 F9c — headless eval smoke：验证训好的 locomotion 策略在平地上真能前进。

go2_eval.py 是 show_viewer=True 无限循环，不适合无人看守。此脚本 headless 跑 N 步，
默认速度指令（cfgs 里 lin_vel_x_range=[0.5,0.5] 前进），记 base x 位移 + z + 是否摔倒
（摔倒会触发 Go2Env 的 termination reset，base 被拉回原点 → dx 变小）。

需在 /work/locomotion 下跑（import go2_env + logs/go2-walking）。
    python go2_eval_smoke.py --backend gpu --steps 250
"""
import argparse
import os
import pickle

import numpy as np
import torch

import genesis as gs
from rsl_rl.runners import OnPolicyRunner

from go2_env import Go2Env


def _np(x):
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-e", "--exp_name", type=str, default="go2-walking")
    ap.add_argument("--ckpt", type=int, default=100)
    ap.add_argument("--steps", type=int, default=250)
    ap.add_argument("--backend", type=str, default="gpu")
    args = ap.parse_args()

    gs.init(backend=getattr(gs, args.backend), precision="32", logging_level="warning")
    log_dir = f"logs/{args.exp_name}"
    with open(f"{log_dir}/cfgs.pkl", "rb") as f:
        env_cfg, obs_cfg, reward_cfg, command_cfg, train_cfg = pickle.load(f)
    reward_cfg["reward_scales"] = {}

    env = Go2Env(1, env_cfg, obs_cfg, reward_cfg, command_cfg, show_viewer=False)
    runner = OnPolicyRunner(env, train_cfg, log_dir, device=gs.device)
    runner.load(os.path.join(log_dir, f"model_{args.ckpt}.pt"))
    policy = runner.get_inference_policy(device=gs.device)

    obs = env.reset()
    p0 = _np(env.robot.get_pos()).reshape(-1).copy()
    xs, zs = [], []
    with torch.no_grad():
        for _ in range(args.steps):
            act = policy(obs)
            obs, _, dones, _ = env.step(act)
            p = _np(env.robot.get_pos()).reshape(-1)
            xs.append(float(p[0]))
            zs.append(float(p[2]))
    xs, zs = np.asarray(xs), np.asarray(zs)
    dx = xs[-1] - p0[0]
    print("=== F9c eval smoke ===", flush=True)
    print(f"start=({p0[0]:.3f},{p0[1]:.3f},{p0[2]:.3f}) steps={args.steps} cmd=lin_vel_x(default)")
    print(f"dx={dx:.3f} final_z={zs[-1]:.3f} min_z={zs.min():.3f} max_z={zs.max():.3f}")
    walked = (dx > 0.5) and (zs.min() > 0.1)
    print("VERDICT:", "WALKS_OK" if walked else "CHECK (fell / no progress)", flush=True)


if __name__ == "__main__":
    main()
