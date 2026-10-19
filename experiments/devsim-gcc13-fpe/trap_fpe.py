# SPDX-License-Identifier: Apache-2.0
"""Run one fork test body with FE_INVALID trapping on for DEVSIM's set_parameter call.

Run under gdb inside the image, from the fork's archive directory (``/work/out``):
    gdb -batch -ex run -ex bt --args python3 trap_fpe.py
With the GCC 13.3 build of DEVSIM, gdb stops with SIGFPE in CPython's ``_Py_dg_dtoa`` (float to
string), called from DEVSIM's ``ObjectHolder::GetString`` while it reads the arguments of
``set_parameter``; DEVSIM's own FPE check would report that flag as "Uncaught FPE: Invalid".
With the PyPI wheel or the GCC 14 build, the test body runs through and prints "no trap".
"""

import ctypes
import functools
import sys

sys.path.insert(0, "/work/out")

import devsim  # noqa: E402

import gplugins.devsim.tests.test_stack1d as test_stack1d  # noqa: E402

FE_INVALID = 1
libm = ctypes.CDLL("libm.so.6")
_set_parameter = devsim.set_parameter


@functools.wraps(_set_parameter)
def _trapping_set_parameter(*args, **kwargs):
    if kwargs.get("name") == "top_bias":
        libm.feenableexcept(FE_INVALID)
    return _set_parameter(*args, **kwargs)


devsim.set_parameter = _trapping_set_parameter
test_stack1d.test_parallel_plate_charge()
print("no trap")
