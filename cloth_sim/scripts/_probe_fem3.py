import inspect
import genesis as gs
print("=== FEMOptions ===")
print(inspect.signature(gs.options.FEMOptions.__init__))
# show fields/defaults
try:
    o = gs.options.FEMOptions()
    for k in ("use_implicit_solver", "enable_vertex_constraints", "damping", "floor_height"):
        print(" ", k, "=", getattr(o, k, "<none>"))
except Exception as e:
    print("inst fail", e)
