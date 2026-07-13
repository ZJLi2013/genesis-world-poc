"""Shared core for the Go2-in-3DGS-kitchen pipeline (feature8).

Go2 counterpart of `franka_kitchen/franka_kitchen_common.py`. Pure-numpy + stdlib
XML (no genesis / vkgs imports) so both the Genesis side (FK / pose sourcing) and
the vk_gs side (render) can import it. Self-contained (the go2_kitchen/ subdir is
independent of franka_kitchen/, which stays frozen). Holds:

  1. Genesis(Z-up) -> splat(Y-up) coordinate mapping  (feature3 kitchen calibration)
  2. kinematic link name -> visual mesh basename       (parsed from go2.urdf)

NOTE on (1): the mapping is a property of the physical kitchen splat (rustic_kitchen),
NOT of the robot, so these constants MUST match franka_kitchen_common's feature3
calibration exactly. Duplicated here (not imported) to keep this subdir self-contained;
if the kitchen calibration is ever re-derived, update BOTH.

Go2 vs Franka notes (feature8 G1):
  - Go2 `<visual>` origins are all identity (checked in go2.urdf) -> per-link
    assumption holds exactly like Franka: each visual mesh sits at its link origin,
    so `link_transform_flat(link_pose)` places it with no per-visual offset.
  - Go2 legs share meshes via mirroring: left legs use thigh/calf, right legs use
    thigh_mirror/calf_mirror, all four hips share hip, all four feet share foot.
    We do NOT hardcode this — `parse_link_mesh_map()` reads it straight from the URDF.
  - Colors: Go2 `.dae` are flat-shaded MULTI-MATERIAL (no textures). We convert to
    `.glb` (go2_dae2glb.py), which preserves each sub-material's baseColor, and load
    it without set_mesh_color. So there is no color table to keep in sync here.
"""
import os
import xml.etree.ElementTree as ET

import numpy as np

# --- 1. Genesis(Z-up) -> splat(Y-up) mapping (feature3; MUST match franka calib) --
# p_splat = R @ p_gen + T ;  R: (x,y,z) -> (x, z, -y) ;  scale s = 1.
# T places the Genesis origin at the splat floor centre.
# Vectors (up / mesh orientation) get R only, no translation.
SPLAT_T = np.array([0.0, -1.1, 0.92])
SPLAT_R = np.array([[1, 0, 0],
                    [0, 0, 1],
                    [0, -1, 0]], dtype=float)

# 12 actuated leg joints (order matches examples/locomotion/go2_env.py).
GO2_JOINT_NAMES = [
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
]
# Nominal standing pose (from go2_kinematic.py), same joint order as above.
GO2_STAND_POSE = [0.0, 0.8, -1.5, 0.0, 0.8, -1.5, 0.0, 1.0, -1.5, 0.0, 1.0, -1.5]


def quat_to_mat(q):
    """wxyz quaternion -> 3x3 rotation matrix."""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z),     2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z),     2 * (y * z - x * w)],
        [2 * (x * z - y * w),         2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _T44(rot, pos):
    m = np.eye(4)
    m[:3, :3] = rot
    m[:3, 3] = pos
    return m


def link_transform_flat(pos_gen, quat_gen):
    """Genesis-world link pose (pos, wxyz quat) -> splat-world 4x4, column-major flat.

    Returns a length-16 list for vkgs `Renderer.set_mesh_transform` (glm column-major):
        M = Translate(T) @ R @ LinkWorldT_gen
    """
    r4 = _T44(SPLAT_R, np.zeros(3))
    tt = _T44(np.eye(3), SPLAT_T)
    link = _T44(quat_to_mat(quat_gen), np.asarray(pos_gen, float))
    m = tt @ r4 @ link
    return m.flatten(order="F").tolist()


def gen_point_to_splat(p):
    """Map a Genesis-world point (e.g. camera eye / lookat) into splat space."""
    return (SPLAT_R @ np.asarray(p, float) + SPLAT_T).tolist()


def gen_vec_to_splat(v):
    """Map a Genesis-world direction (e.g. camera up) into splat space (R only)."""
    return (SPLAT_R @ np.asarray(v, float)).tolist()


def parse_link_mesh_map(urdf_path):
    """go2.urdf -> {link_name: mesh_basename} for links carrying a <visual><mesh>.

    Robust to the left/right mesh mirroring (reads the actual filename per link),
    so callers never hardcode which leg uses thigh vs thigh_mirror.
    """
    root = ET.parse(urdf_path).getroot()
    out = {}
    for link in root.findall("link"):
        name = link.get("name")
        mesh = link.find("./visual/geometry/mesh")
        if name is None or mesh is None:
            continue
        fn = mesh.get("filename", "")
        base = os.path.splitext(os.path.basename(fn))[0]
        if base:
            out[name] = base
    return out
