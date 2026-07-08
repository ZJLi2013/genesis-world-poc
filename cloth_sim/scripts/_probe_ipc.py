import torch
print("torch", torch.__version__, "cuda_avail", torch.cuda.is_available())
import genesis as gs
print("genesis", gs.__version__)
opts = [o for o in dir(gs.options) if o.endswith("Options")]
print("options:", opts)
try:
    import pyuipc
    print("pyuipc import OK", getattr(pyuipc, "__version__", "?"))
except Exception as e:
    print("pyuipc import FAIL:", repr(e))
# probe IPC coupler entry
print("has CouplerOptions:", hasattr(gs.options, "CouplerOptions"))
print("has IPCCouplerOptions:", hasattr(gs.options, "IPCCouplerOptions"))
