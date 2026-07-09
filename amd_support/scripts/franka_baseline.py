"""F1 硬件矩阵复现：最小 Franka scene.build()+step。

取自上游 genesis-world #2962 的 minimal reproduction（纯 Genesis，无第三方代码）：
带凸分解碰撞几何的关节机器人（Franka Panda）在 gfx942 上 scene.build() SIGSEGV，
gfx950 正常。本脚本用于在任意 AMD arch 上跑同一最小用例，扩展硬件矩阵。

用法：
    python -u franka_baseline.py ; echo "EXIT=$?"

打印 ENTITIES_ADDED / BUILD_OK / STEP_OK 三个里程碑；
若进程以 139 (SIGSEGV) 退出且 BUILD_OK 未打印 → 复现 #2962 崩溃。
"""
import genesis as gs

gs.init(backend=gs.gpu, logging_level="warning")
scene = gs.Scene(show_viewer=False)
scene.add_entity(gs.morphs.Plane())
scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
print("ENTITIES_ADDED", flush=True)
scene.build()
print("BUILD_OK", flush=True)
for _ in range(10):
    scene.step()
print("STEP_OK", flush=True)
