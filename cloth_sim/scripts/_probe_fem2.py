import inspect
from genesis.engine.entities.fem_entity import FEMEntity

for name in ("set_vertex_constraints", "update_constraint_targets", "remove_vertex_constraints",
             "set_position", "set_velocity"):
    fn = getattr(FEMEntity, name, None)
    if fn is None:
        print(name, "MISSING"); continue
    try:
        print("===", name, inspect.signature(fn))
    except Exception as e:
        print("===", name, "sig-fail", e)
    doc = (fn.__doc__ or "").strip()
    if doc:
        print("   doc:", doc[:400].replace("\n", " "))
