"""临时：自省 Genesis 1.1.1 的 PBD/材质/场景 API，修正脚本用。跑完即删。"""
import inspect
import genesis as gs


def show_fields(name, obj):
    print(f"\n=== {name} ===")
    mf = getattr(obj, "model_fields", None)
    if mf:
        for k, v in mf.items():
            print(f"  {k}: default={getattr(v, 'default', '?')}")
        return
    try:
        print("  signature:", inspect.signature(obj))
    except (TypeError, ValueError):
        print("  (no signature)", [a for a in dir(obj) if not a.startswith("_")][:40])


show_fields("options.SimOptions", gs.options.SimOptions)
show_fields("options.PBDOptions", gs.options.PBDOptions)
print("\n=== materials.PBD members ===")
print([a for a in dir(gs.materials.PBD) if not a.startswith("_")])
show_fields("materials.PBD.Cloth", gs.materials.PBD.Cloth)
print("\n=== morphs members ===")
print([a for a in dir(gs.morphs) if not a.startswith("_")])
show_fields("morphs.Mesh", gs.morphs.Mesh)
print("\n=== Scene.add_entity ===")
print(" ", inspect.signature(gs.Scene.add_entity))
print("=== Scene.add_camera ===")
print(" ", inspect.signature(gs.Scene.add_camera))
