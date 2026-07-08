import glob, sys
import imageio.v2 as iio

d = sys.argv[1] if len(sys.argv) > 1 else "output/feature5/ripped_final"
out = sys.argv[2] if len(sys.argv) > 2 else d + ".mp4"
fs = sorted(glob.glob(d + "/frame_*.png"))
w = iio.get_writer(out, fps=60)
for f in fs:
    w.append_data(iio.imread(f))
w.close()
print("frames", len(fs), "->", out)
