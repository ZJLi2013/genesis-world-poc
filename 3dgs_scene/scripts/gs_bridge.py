"""gs_bridge -- Genesis camera pose <-> vk_gs INRIA camera preset bridge (feature3).

Pure stdlib + numpy. Reused by M0/M0b. Two responsibilities:
  1. pose_to_inria(): (eye, lookat, up) -> one vk_gs INRIA-preset dict, exact
     inverse of vk_gs `importCamerasINRIA` (camera_set.h:226-279). Verified against
     the working M0a cams.json (up=Y, fov 60deg -> fx=fy=1108.5 @ w=1280).
  2. genesis_to_splat(): map a Genesis (Z-up) world pose into the vk_gs/splat
     (Y-up) world frame, so real Genesis poses land on the M0a splat scene.

vk_gs preset schema (list of these):
  {id, img_name, width, height, position[3], rotation[3][3], fx, fy}
Importer decode (what vk_gs does):
  eye = (pos.x, -pos.y, -pos.z);  up = col1(rot);  at = col2(rot);  ctr = eye + at
  (rotation is [row][col]; col0 unused). So the encode below is its inverse.
"""
import math
import numpy as np

# Genesis(Z-up) -> vk_gs/splat(Y-up): rotate -90deg about X, (x,y,z)->(x,z,-y).
R_GENESIS_TO_SPLAT = np.array([[1.0, 0.0, 0.0],
                               [0.0, 0.0, 1.0],
                               [0.0, -1.0, 0.0]], dtype=np.float64)


def _unit(v):
    v = np.asarray(v, dtype=np.float64).reshape(3)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError(f"degenerate vector {v}")
    return v / n


def focal_from_fov(fov_deg, pixels):
    """Pinhole focal (px) for a given fov (deg) across `pixels` extent."""
    return 0.5 * pixels / math.tan(0.5 * math.radians(fov_deg))


def pose_to_inria(eye, lookat, up, cam_id=0, width=1280, height=720,
                  fov_deg=60.0, fx=None, fy=None, img_name=None):
    """Encode a target (eye, lookat, up) into a vk_gs INRIA preset dict."""
    eye = np.asarray(eye, dtype=np.float64).reshape(3)
    lookat = np.asarray(lookat, dtype=np.float64).reshape(3)
    d = _unit(lookat - eye)          # view direction
    u = _unit(up)                    # up (assumed ~orthonormal; Genesis gives this)
    if fx is None:
        fx = focal_from_fov(fov_deg, width)
    if fy is None:
        fy = fx                      # square pixels unless caller overrides

    rot = [[0.0, 0.0, 0.0] for _ in range(3)]
    # col1 = up  (importer: up = col1; encode with x negated)
    rot[0][1] = -u[0]; rot[1][1] = u[1]; rot[2][1] = u[2]
    # col2 = at/view dir (importer: at = col2; encode with y,z negated)
    rot[0][2] = d[0]; rot[1][2] = -d[1]; rot[2][2] = -d[2]
    # col0 unused by importer -> leave zeros

    return {
        "id": int(cam_id),
        "img_name": img_name or f"cam_{cam_id:04d}",
        "width": int(width),
        "height": int(height),
        "position": [float(eye[0]), float(-eye[1]), float(-eye[2])],
        "rotation": rot,
        "fx": float(fx),
        "fy": float(fy),
    }


def genesis_to_splat(eye, lookat, up, center=(0.0, 0.0, 0.0), scale=1.0,
                     R=R_GENESIS_TO_SPLAT):
    """Map a Genesis (Z-up) world pose into the splat (Y-up) frame.

    Similarity transform  p_splat = scale * (R @ p_genesis) + center  (E2):
      R      -- axis alignment Z-up -> Y-up (default (x,y,z)->(x,z,-y))
      scale  -- Genesis metre -> splat units (M0b used scale=1)
      center -- translation t (e.g. kitchen floor centre)
    Points are scaled+rotated+translated; the up vector is rotated only.
    Returns (eye', lookat', up') as numpy arrays.
    """
    R = np.asarray(R, dtype=np.float64)
    t = np.asarray(center, dtype=np.float64).reshape(3)
    s = float(scale)
    eye = s * (R @ np.asarray(eye, dtype=np.float64).reshape(3)) + t
    lookat = s * (R @ np.asarray(lookat, dtype=np.float64).reshape(3)) + t
    up = R @ np.asarray(up, dtype=np.float64).reshape(3)
    return eye, lookat, up


def build_cams_json(poses, width=1280, height=720, fov_deg=60.0):
    """poses: list of (eye, lookat, up) -> list of INRIA preset dicts."""
    return [pose_to_inria(e, l, u, cam_id=i, width=width, height=height,
                          fov_deg=fov_deg)
            for i, (e, l, u) in enumerate(poses)]


def build_sequence_cfg(n, out_dir, out_prefix="m0b", pipeline=1, frames=100,
                       warmup=200, preset_offset=1):
    """Build vk_gs benchmark sequence text.

    setHomePreset inserts a home cam at index 0, pushing loaded presets to
    1..N, hence preset_offset=1. A no-save warmup SEQUENCE lets the async PLY
    upload finish before the first real frame (fixes blank first frame).
    """
    blocks = []
    if warmup > 0:
        blocks.append("\n".join([
            'SEQUENCE "warmup"',
            f"--sequenceframes {warmup}",
            f"--pipeline {pipeline}",
            f"--activateCameraPreset {preset_offset}",
            "",
        ]))
    for i in range(n):
        blocks.append("\n".join([
            f'SEQUENCE "{out_prefix}_{i:04d}"',
            f"--sequenceframes {frames}",
            f"--pipeline {pipeline}",
            f"--activateCameraPreset {i + preset_offset}",
            f"--saveImage {out_dir}/{out_prefix}_{i:04d}.png",
            "",
        ]))
    return "\n".join(blocks) + "\n"
