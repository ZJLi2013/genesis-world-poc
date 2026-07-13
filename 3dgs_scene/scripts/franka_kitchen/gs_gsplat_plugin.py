"""gs_gsplat_plugin -- Genesis in-loop camera sensor backed by the vk_gs
Gaussian-splatting renderer (feature6 S1).

Importing this module registers `GsplatCameraOptions` with Genesis' sensor
system (via `Sensor.__init_subclass__`), so user code can do:

    import gs_gsplat_plugin                       # registers the sensor
    from gs_gsplat_plugin import GsplatCameraOptions
    cam = scene.add_sensor(GsplatCameraOptions(res=(1280, 720),
                                               ply=..., assets=...,
                                               robot_entity_idx=1))
    scene.build()
    scene.step()
    rgb = cam.read().rgb            # (H, W, 3) uint8 torch tensor

Design (S1, KISS — reuses the feature5 offline core):
  - Backend-agnostic: this sensor only reads link world poses + drives vk_gs, so
    it works with either physics backend. The runner picks it via gs.init;
    feature6 defaults to `gs.gpu` (physics + render same card, Gate B verified),
    with `gs.cpu` as fallback (see feature6.2). Use a compute-healthy GPU.
  - One shared `vkgs.Renderer` per sensor class (in shared_metadata), loaded
    with the kitchen splat + every Franka visual .obj colored per its MJCF
    material (franka_kitchen_common).
  - Control inversion: Genesis drives the render lazily on `cam.read()` after
    each `scene.step()` (BaseCameraSensor staleness keyed off `scene.t`).
  - Pose same-source: link world poses are read live from the tracked entity
    in the same scene (no JSON round-trip), mapped Genesis->splat and pushed
    via `set_mesh_transform`.
  - Camera is static in SPLAT space (cam_eye/center/up/fovy); not link-attached.

Must sit next to `franka_kitchen_common.py`. Needs the built `vkgs` module on
`sys.path` (set VKGS_BUILD or add it before importing this module).
"""
import glob
import os
from dataclasses import dataclass, field
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

import franka_kitchen_common as fkc


# ============================== Options ==============================
class GsplatCameraOptions(BaseCameraOptions["GsplatCameraSensor"]):
    """Options for the vk_gs Gaussian-splatting camera sensor.

    `cam_*` fields are in SPLAT space (already feature3-mapped), consumed
    directly by `vkgs.Renderer.set_camera`; the inherited `pos/lookat/up/fov`
    (Genesis world frame) are unused in S1.
    """

    ply: str = "/work/assets/rustic_kitchen_2m.ply"
    assets: str = "/work/assets/franka"
    robot_entity_idx: int = 1               # which scene entity's links to render
    gpu: int = 1                            # Vulkan device index for the renderer
    render_steps: int = 5                   # renderer warm steps per frame
    cam_eye: Vec3FType = (0.0, -0.125, -0.28)
    cam_center: Vec3FType = (0.0, -0.425, 1.82)
    cam_up: Vec3FType = (0.0, 1.0, 0.0)
    cam_fovy: float = 65.0


# ============================== Shared metadata ==============================
@dataclass
class GsplatCameraSharedMetadata(KinematicSensorMetadataMixin, SharedSensorMetadata):
    """Per-class shared state: the single vk_gs renderer + its mesh instances."""

    renderer: Optional[Any] = None
    sensors: Optional[list] = None
    image_cache: Optional[dict] = None
    instances: Optional[list] = None        # list of (mesh_idx, link_name)
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
class GsplatCameraSensor(
    BaseCameraSensor,
    Sensor[GsplatCameraOptions, None, GsplatCameraSharedMetadata, CameraReturnType],
):
    """In-loop camera sensor that renders the tracked robot into the 3DGS scene."""

    uses_ring_pipeline: ClassVar[bool] = False

    def __init__(self, options, idx, shared_context, shared_metadata, manager):
        super().__init__(options, idx, shared_context, shared_metadata, manager)
        self._options: GsplatCameraOptions

    # ------------------------------ lifecycle ------------------------------
    def build(self):
        super().build()  # KinematicSensorMixin (attach/offsets) -> Sensor.build
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

    def _init_renderer(self, opt: GsplatCameraOptions):
        import vkgs

        w, h = opt.res
        r = vkgs.Renderer(ply=opt.ply, width=w, height=h, gpu=opt.gpu)
        r.set_camera(eye=list(opt.cam_eye), center=list(opt.cam_center),
                     up=list(opt.cam_up), fovy=opt.cam_fovy)

        # Instantiate every Franka visual .obj once, colored per MJCF material.
        instances = []  # (mesh_idx, link_name)
        for path in sorted(glob.glob(os.path.join(opt.assets, "*.obj"))):
            base = os.path.basename(path)
            if "collision" in base:
                continue
            stem = base[:-4]
            marker = fkc.link_of(stem)
            if marker is None:
                continue
            col = fkc.color_of(stem)
            targets = fkc.FINGER_LINKS if marker == "finger" else (marker,)
            for link_name in targets:
                m_idx = r.add_mesh(path)
                if m_idx < 0:
                    continue
                if col is not None:
                    r.set_mesh_color(m_idx, col)
                instances.append((m_idx, link_name))

        self._shared_metadata.renderer = r
        self._shared_metadata.instances = instances

    # ------------------------------ render ------------------------------
    def _apply_camera_transform(self, camera_T: torch.Tensor):
        # S1 camera is static in splat space; link attachment unused.
        pass

    def _render_current_state(self):
        r = self._shared_metadata.renderer
        entity = self._shared_metadata.robot_entity

        # Live link world poses (same-source, no JSON). relative=True matches the
        # proven feature5 franka_fk_dump path (franka base at origin).
        link_pose = {}
        for link in entity.links:
            pos = _to_np(link.get_pos())[:3]
            quat = _to_np(link.get_quat())[:4]  # wxyz
            link_pose[link.name] = (pos, quat)

        for m_idx, link_name in self._shared_metadata.instances:
            lp = link_pose.get(link_name)
            if lp is None:
                continue
            r.set_mesh_transform(m_idx, fkc.link_transform_flat(lp[0], lp[1]))

        for _ in range(self._options.render_steps):
            r.step()

        rgb = np.ascontiguousarray(r.readback()[..., :3])
        rgb_t = torch.as_tensor(rgb, device=gs.device).to(torch.uint8)
        self._shared_metadata.image_cache[self._idx][:] = rgb_t


def _to_np(x):
    return (x.cpu().numpy() if hasattr(x, "cpu") else np.asarray(x)).reshape(-1)
