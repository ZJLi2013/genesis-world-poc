"""把帧序列(frame_*.png)合成 mp4。自动选用 imageio / opencv。

用法: python scripts/make_video.py [frames_dir] [out.mp4] [fps]
"""
import glob
import os
import sys


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "output/feature3/grasp"
    out = sys.argv[2] if len(sys.argv) > 2 else "output/feature3/feature3_grasp.mp4"
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    files = sorted(glob.glob(os.path.join(d, "frame_*.png")))
    if not files:
        print(f"[video] no frames in {d}"); return
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    print(f"[video] {len(files)} frames -> {out} @ {fps}fps")

    # 优先 imageio(+ffmpeg)，否则退回 opencv
    try:
        import imageio.v2 as imageio
        w = imageio.get_writer(out, fps=fps, codec="libx264",
                               pixelformat="yuv420p", macro_block_size=None)
        for f in files:
            w.append_data(imageio.imread(f))
        w.close()
        print(f"[video] done via imageio: {out} ({os.path.getsize(out)} bytes)")
        return
    except Exception as e:  # noqa: BLE001
        print(f"[video] imageio failed: {e}; trying opencv")

    import cv2
    import numpy as np  # noqa: F401
    frame0 = cv2.imread(files[0])
    h, wd = frame0.shape[:2]
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (wd, h))
    for f in files:
        vw.write(cv2.imread(f))
    vw.release()
    print(f"[video] done via opencv: {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
