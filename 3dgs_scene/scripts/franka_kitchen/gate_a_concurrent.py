"""Gate A: concurrent HIP compute + Vulkan render on the same AMD GPU.

Ephemeral (feature6 single-card concurrency verification). Decoupled from
genesis/quadrants. Compute runs in a SEPARATE PROCESS (torch ROCm matmul loop)
to avoid GIL starvation from the vk_gs C-extension render loop; the main process
drives a vk_gs (Vulkan/RADV) render loop. Both pinned to the same physical GPU.
Goal: see whether sustained compute+graphics coexistence wedges the card
(MES hang / VK_ERROR_DEVICE_LOST) on this kernel/firmware.

Run inside vkgs_build (genesis-nyx-amd:latest). --gpu N pins both the compute
child (HIP_VISIBLE_DEVICES=N -> torch cuda:0) and the vkgs renderer to physical
GPU N. Use a compute-healthy card (GPU1 was wedged 2026-07-13; GPU2 is healthy).
"""
import argparse
import os
import subprocess
import sys
import time
import traceback

COMPUTE_SNIPPET = r"""
import time, torch
dev = torch.device("cuda:0")
n = 4096
a = torch.randn(n, n, device=dev); b = torch.randn(n, n, device=dev)
it = 0; t0 = time.time()
print("COMPUTE_READY name=" + torch.cuda.get_device_name(0), flush=True)
while True:
    c = a @ b; a = c * 1e-4 + b; torch.cuda.synchronize(); it += 1
    if it % 50 == 0:
        open("/tmp/ga_compute.txt", "w").write(str(it))
"""


def ensure_display():
    if os.environ.get("DISPLAY"):
        return
    if subprocess.run(["which", "Xvfb"], capture_output=True).returncode != 0:
        return
    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x1024x24", "-ac", "+extension", "GLX"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["DISPLAY"] = ":99"
    time.sleep(2)


def compute_iters():
    try:
        return int(open("/tmp/ga_compute.txt").read().strip())
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--ply", default="/work/assets/rustic_kitchen_2m.ply")
    ap.add_argument("--gpu", type=int, default=1)
    ap.add_argument("--res", type=int, nargs=2, default=[1280, 720])
    args = ap.parse_args()

    print("=== Gate A: concurrent HIP compute (subproc) + Vulkan render (same GPU) ===", flush=True)
    if os.path.exists("/tmp/ga_compute.txt"):
        os.remove("/tmp/ga_compute.txt")
    ensure_display()

    # Compute child (separate process, own HIP context, same physical GPU).
    env = dict(os.environ, HIP_VISIBLE_DEVICES=str(args.gpu))
    child = subprocess.Popen([sys.executable, "-u", "-c", COMPUTE_SNIPPET], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # Give the child a head start so its HIP context is live before we render.
    time.sleep(8)
    print(f"compute child pid={child.pid} alive={child.poll() is None} iters={compute_iters()}", flush=True)

    sys.path.insert(0, os.environ.get("VKGS_BUILD", "/work/vk_gaussian_splatting/build"))
    import vkgs
    w, h = args.res
    r = vkgs.Renderer(ply=args.ply, width=w, height=h, gpu=args.gpu)
    r.set_camera(eye=[0.0, -0.125, -0.28], center=[0.0, -0.425, 1.82], up=[0.0, 1.0, 0.0], fovy=65.0)
    print(f"renderer ready splat={r.splat_count()}", flush=True)

    frames = 0
    render_err = None
    t0 = time.time()
    last_hb = t0
    try:
        while time.time() - t0 < args.seconds:
            r.step()
            _ = r.readback()
            frames += 1
            now = time.time()
            if now - last_hb >= 10:
                print(f"[{now-t0:5.1f}s] render_frames={frames} compute_iters={compute_iters()} "
                      f"child_alive={child.poll() is None}", flush=True)
                last_hb = now
    except Exception as e:  # noqa
        render_err = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    ci = compute_iters()
    child_rc = child.poll()
    child.terminate()
    try:
        child_out = child.communicate(timeout=5)[0]
    except Exception:
        child.kill()
        child_out = ""

    dt = time.time() - t0
    print(f"=== DONE {dt:.1f}s render_frames={frames} ({frames/dt:.1f} fps) "
          f"compute_iters={ci} child_rc_during_run={child_rc} ===", flush=True)
    print(f"RENDER_ERR={render_err}", flush=True)
    tail = "\n".join((child_out or "").splitlines()[-8:])
    print(f"COMPUTE_CHILD_TAIL:\n{tail}", flush=True)
    print("GATE_A_DONE", flush=True)


if __name__ == "__main__":
    main()
