"""Shared core for the Franka-in-3DGS-kitchen pipeline (feature5).

Pure-numpy, no genesis / vkgs imports, so both the Genesis side
(`franka_fk_dump.py`) and the vk_gs side (`franka_render_kitchen.py`)
can import it. Holds the three things that must stay in sync across the
two containers:

  1. Genesis(Z-up) -> splat(Y-up) coordinate mapping   (feature3 calibration)
  2. Franka visual `.obj` -> MJCF material color        (panda.xml)
  3. `.obj` basename -> kinematic link name             (per-link FK transform)

See docs/exp/part5-exp.md (F1 / F1.1) for the derivation and evidence.
"""
import re

import numpy as np

# --- 1. Genesis(Z-up) -> splat(Y-up) mapping (feature3) --------------------
# p_splat = R @ p_gen + T ;  R: (x,y,z) -> (x, z, -y) ;  scale s = 1.
# T places the Genesis origin at the splat floor centre.
# Vectors (up / mesh orientation) get R only, no translation.
SPLAT_T = np.array([0.0, -1.1, 0.92])
SPLAT_R = np.array([[1, 0, 0],
                    [0, 0, 1],
                    [0, -1, 0]], dtype=float)


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

    Returns a length-16 list suitable for vkgs `Renderer.set_mesh_transform`
    (glm column-major). Same value the F1 render used:
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


# --- 2. MJCF material colors (franka_emika_panda/panda.xml <asset>) --------
# rgba are sRGB display values. vk_gs shades in LINEAR space (obj_loader does
# pow(baseColor, 2.2) for OBJ), so convert sRGB -> linear before set_mesh_color.
MAT_SRGB = {
    "white":      (1.0, 1.0, 1.0),
    "off_white":  (0.901961, 0.921569, 0.929412),
    "black":      (0.25, 0.25, 0.25),
    "green":      (0.0, 1.0, 0.0),
    "light_blue": (0.039216, 0.541176, 0.780392),
}

# `.obj` basename (no extension) -> material name, transcribed from the
# <geom mesh=".." material=".."> entries in panda.xml.
MESH_MATERIAL = {
    "link0_0": "off_white", "link0_1": "black", "link0_2": "off_white", "link0_3": "black",
    "link0_4": "off_white", "link0_5": "black", "link0_7": "white", "link0_8": "white",
    "link0_9": "black", "link0_10": "off_white", "link0_11": "white",
    "link1": "white", "link2": "white",
    "link3_0": "white", "link3_1": "white", "link3_2": "white", "link3_3": "black",
    "link4_0": "white", "link4_1": "white", "link4_2": "black", "link4_3": "white",
    "link5_0": "black", "link5_1": "white", "link5_2": "white",
    "link6_0": "off_white", "link6_1": "white", "link6_2": "black", "link6_3": "white",
    "link6_4": "white", "link6_5": "white", "link6_6": "white", "link6_7": "light_blue",
    "link6_8": "light_blue", "link6_9": "black", "link6_10": "black", "link6_11": "white",
    "link6_12": "green", "link6_13": "white", "link6_14": "black", "link6_15": "black",
    "link6_16": "white",
    "link7_0": "white", "link7_1": "black", "link7_2": "black", "link7_3": "black",
    "link7_4": "black", "link7_5": "black", "link7_6": "black", "link7_7": "white",
    "hand_0": "off_white", "hand_1": "black", "hand_2": "black", "hand_3": "white", "hand_4": "off_white",
    "finger_0": "off_white", "finger_1": "black",
}


def color_of(basename):
    """`.obj` basename (no extension) -> LINEAR rgb list, or None if unmapped."""
    mat = MESH_MATERIAL.get(basename)
    if mat is None:
        return None
    return [v ** 2.2 for v in MAT_SRGB[mat]]  # sRGB -> linear


# --- 3. `.obj` basename -> kinematic link name -----------------------------
# Visual geoms carry no per-geom pos/quat in panda.xml, so every `.obj` of a
# link shares that link's world transform (per-link assumption, verified F1).
def link_of(basename):
    """`.obj` basename (no extension) -> link name, or None to skip.

    Note: `finger_*` maps to BOTH fingers; callers must instantiate it twice
    (left_finger / right_finger). This helper returns "finger" as a marker.
    """
    if basename.startswith("hand_"):
        return "hand"
    if basename.startswith("finger_"):
        return "finger"
    m = re.match(r"(link\d+)_?", basename)
    return m.group(1) if m else None


FINGER_LINKS = ("left_finger", "right_finger")
