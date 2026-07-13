"""go2_gsplat_plugin -- Genesis in-loop camera sensor for the Unitree Go2, backed
by the vk_gs Gaussian-splatting renderer (feature8 G1).

Independent Go2 counterpart of `franka_kitchen/gs_gsplat_plugin.py`. Kept SEPARATE
on purpose (own Options/Sensor classes, own `go2_kitchen_common` assembly) so the
proven Franka path is never touched. Importing this module registers
`Go2GsplatCameraOptions` with Genesis' sensor system:

    import go2_gsplat_plugin
    from go2_gsplat_plugin import Go2GsplatCameraOptions
    cam = scene.add_sensor(Go2GsplatCameraOptions(res=(1280, 720), gpu=2,
                                                  robot_entity_idx=1))
    scene.build(); scene.step(); rgb = cam.read().rgb

Go2 vs Franka assembly differences (feature8):
  - Meshes come from Go2 `.dae` converted to `.glb` (go2_dae2glb.py) under
    `assets`. Go2 `.dae` are FLAT-SHADED MULTI-MATERIAL (no texture images): base
    alone has a silver top shell + white accents + near-black body. glb preserves
    each sub-material's baseColor, so we load it AS-IS and DO NOT `set_mesh_color`
    (a single override would flatten it back into one grey blob).
  - link->mesh is parsed from `go2.urdf` (go2_kitchen_common.parse_link_mesh_map);
    the 4 legs share meshes (hip/thigh(+mirror)/calf(+mirror)/foot), so one glb
    file is `add_mesh`'d once per link that uses it (each gets its own transform).
  - Coordinate bridge + link_transform_flat live in `go2_kitchen_common` (a
    self-contained copy of the feature3 kitchen calibration; go2_kitchen/ does not
    import from franka_kitchen/).

Camera is static in SPLAT space for G1a (egocentric follow = later G1c, fill
`_apply_camera_transform`). Must sit next to `go2_kitchen_common.py`; needs the
built `vkgs` module on sys.path.
"""
import os
from dataclasses import dataclass
from typing import Any, ClassVar, Optional

import numpy as np
import torch

import genesis as gs
from genesis.engine.sensors.base_sensor import (
    KinematicSensorMetadataMixin,
    Sensor,
    SharedSensorMetadata,
)
from genesis.engine.sensors.camera import BaseCameraSensor, CameraReturnType
from genesis.options.sensors.camera import BaseCameraOptions
from genesis.typing import Vec3FType

import go2_kitchen_common as gkc


# ============================== Options ==============================
class Go2GsplatCameraOptions(BaseCameraOptions["Go2GsplatCameraSensor"]):
    """Options for the Go2 vk_gs Gaussian-splatting camera sensor.

    `cam_*` are SPLAT space (feature3-mapped), consumed by `Renderer.set_camera`.
    `urdf` empty -> resolved to the Genesis-shipped go2.urdf at build time.
    """

    ply: str = "/work/assets/rustic_kitchen_2m.ply"
    assets: str = "/work/assets/go2"          # dir of Go2 .glb (multi-material)
    urdf: str = ""                            # go2.urdf for link->mesh map ("" = genesis default)
    robot_entity_idx: int = 1
    gpu: int = 2                              # Vulkan device (GPU1 wedged; use healthy card)
    render_steps: int = 5
    cam_eye: Vec3FType = (0.0, -0.125, -0.28)
    cam_center: Vec3FType = (0.0, -0.425, 1.82)
    cam_up: Vec3FType = (0.0, 1.0, 0.0)
    cam_fovy: float = 65.0

    # 跟拍相机（feature9）：每帧把机位钉到 go2 base（Genesis 坐标）+ 偏移，再映射到
    # splat。默认站在 go2 后方 -y、抬高，看向前方 +y，随 go2 前进而后退 → 走进厨房深处。
    cam_follow: bool = False
    follow_eye_off: Vec3FType = (0.0, -1.0, 0.8)     # gen: 后方 1m + 抬高 0.8m
    follow_center_off: Vec3FType = (0.0, 0.8, 0.1)   # gen: 看向前方 0.8m
    cam_up_gen: Vec3FType = (0.0, 0.0, 1.0)


# ============================== Shared metadata ==============================
@dataclass
class Go2GsplatCameraSharedMetadata(KinematicSensorMetadataMixin, SharedSensorMetadata):
    renderer: Optional[Any] = None
    sensors: Optional[list] = None
    image_cache: Optional[dict] = None
    instances: Optional[list] = None          # list of (mesh_idx, link_name)
    robot_entity: Optional[Any] = None
    last_render_timestep: int = -1

    def destroy(self):
        super().destroy()
        self.renderer = None
        self.sensors = None
        self.image_cache = None
        self.instances = None
        self.robot_entity = None


# ============================== Sensor ==============================
class Go2GsplatCameraSensor(
    BaseCameraSensor,
    Sensor[Go2GsplatCameraOptions, None, Go2GsplatCameraSharedMetadata, CameraReturnType],
):
    """In-loop camera sensor rendering the tracked Go2 into the 3DGS scene."""

    uses_ring_pipeline: ClassVar[bool] = False

    def __init__(self, options, idx, shared_context, shared_metadata, manager):
        super().__init__(options, idx, shared_context, shared_metadata, manager)
        self._options: Go2GsplatCameraOptions

    # ------------------------------ lifecycle ------------------------------
    def build(self):
        super().build()
        scene = self._manager._sim.scene
        opt = self._options

        if self._shared_metadata.sensors is None:
            self._shared_metadata.sensors = []
            self._shared_metadata.image_cache = {}
            self._init_renderer(opt)
            self._shared_metadata.robot_entity = scene.entities[opt.robot_entity_idx]

        self._shared_metadata.sensors.append(self)

        _B = max(self._manager._sim.n_envs, 1)
        w, h = opt.res
        self._shared_metadata.image_cache[self._idx] = torch.zeros(
            (_B, h, w, 3), dtype=torch.uint8, device=gs.device
        )

    def _init_renderer(self, opt: Go2GsplatCameraOptions):
        import vkgs

        w, h = opt.res
        r = vkgs.Renderer(ply=opt.ply, width=w, height=h, gpu=opt.gpu)
        r.set_camera(eye=list(opt.cam_eye), center=list(opt.cam_center),
                     up=list(opt.cam_up), fovy=opt.cam_fovy)

        urdf = opt.urdf or os.path.join(gs.utils.get_assets_dir(), "urdf/go2/urdf/go2.urdf")
        link_mesh = gkc.parse_link_mesh_map(urdf)                 # {link: mesh_basename}

        # One add_mesh per link (legs share glb files -> multiple instances, each
        # driven by that link's own transform). No set_mesh_color: the glb carries
        # per-sub-material baseColors (silver/white/black), which we want to keep.
        instances = []
        for link_name, base in link_mesh.items():
            glb = os.path.join(opt.assets, base + ".glb")
            if not os.path.exists(glb):
                continue
            m_idx = r.add_mesh(glb)
            if m_idx < 0:
                continue
            instances.append((m_idx, link_name))

        self._shared_metadata.renderer = r
        self._shared_metadata.instances = instances

    # ------------------------------ render ------------------------------
    def _apply_camera_transform(self, camera_T: torch.Tensor):
        # G1a: camera static in splat space (egocentric follow -> later G1c).
        pass

    def _render_current_state(self):
        r = self._shared_metadata.renderer
        entity = self._shared_metadata.robot_entity
        opt = self._options

        if opt.cam_follow:
            base = _to_np(entity.get_pos())[:3]                 # gen base pos
            eye_gen = base + np.asarray(opt.follow_eye_off, dtype=float)
            ctr_gen = base + np.asarray(opt.follow_center_off, dtype=float)
            r.set_camera(eye=list(gkc.gen_point_to_splat(eye_gen)),
                         center=list(gkc.gen_point_to_splat(ctr_gen)),
                         up=list(gkc.gen_vec_to_splat(np.asarray(opt.cam_up_gen, dtype=float))),
                         fovy=opt.cam_fovy)

        link_pose = {}
        for link in entity.links:
            pos = _to_np(link.get_pos())[:3]
            quat = _to_np(link.get_quat())[:4]   # wxyz
            link_pose[link.name] = (pos, quat)

        for m_idx, link_name in self._shared_metadata.instances:
            lp = link_pose.get(link_name)
            if lp is None:
                continue
            r.set_mesh_transform(m_idx, gkc.link_transform_flat(lp[0], lp[1]))

        for _ in range(self._options.render_steps):
            r.step()

        rgb = np.ascontiguousarray(r.readback()[..., :3])
        rgb_t = torch.as_tensor(rgb, device=gs.device).to(torch.uint8)
        self._shared_metadata.image_cache[self._idx][:] = rgb_t


def _to_np(x):
    return (x.cpu().numpy() if hasattr(x, "cpu") else np.asarray(x)).reshape(-1)
