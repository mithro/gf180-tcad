<!-- SPDX-License-Identifier: Apache-2.0 -->
# DEVSIM built with GCC 13.3: "Uncaught FPE: Invalid"

The first version of the dev-HEAD TCAD image ([`docker/tcad-dev/`](../../docker/tcad-dev)) compiled
[DEVSIM](https://devsim.org/) with the base image's GCC 13.3. In that image, 13 tests of
[the gplugins fork](https://github.com/mithro/gplugins) failed with
`devsim_py3.error: Uncaught FPE: There was an uncaught floating point exception of type "Invalid"`.
The tests passed with the PyPI wheel and with a build from the same sources using GCC 14. GCC 14
is what [upstream's release build](https://github.com/devsim/devsim/blob/ec9905bbfdfacaf66e0cae7f2d98748f9bb8aeb0/scripts/build_manylinux_2_28.sh)
uses, and the image now uses it too. This directory makes that evidence re-runnable.

| File | What it is |
|---|---|
| [`run.sh`](run.sh) | The whole recipe: build, wheel swap, gdb trap and compiler swap. Each step checks its expected outcome. |
| [`trap_fpe.py`](trap_fpe.py) | Runs the fork's [`test_parallel_plate_charge`](https://github.com/mithro/gplugins/blob/dddaa071321c5177c8471312c565ad86d4b245d7/gplugins/devsim/tests/test_stack1d.py) body with `FE_INVALID` trapping on for DEVSIM's `set_parameter`, for gdb. |

```sh
experiments/devsim-gcc13-fpe/run.sh "$(mktemp -d)"
```

It needs [Docker](https://docs.docker.com/), the sandbox ([`tools/sandbox-run`](../../tools/sandbox-run),
set up by [`tools/sandbox-setup`](../../tools/sandbox-setup)), and network access for the image
build and one PyPI download. The steps are:

1. Build the GCC 13.3 image: [`docker/tcad-dev/build`](../../docker/tcad-dev/build) `--load`,
   run in a worktree at commit
   [`7c89045`](https://github.com/mithro/gf180-tcad/commit/7c89045), the last commit that used
   GCC 13.3.
2. Take the fork at the pinned submodule commit, as a `git archive`.
3. Run the test in that image. It fails with "Uncaught FPE".
4. **Wheel swap.** Put the PyPI `devsim` 2.11.1 wheel on `PYTHONPATH` in the same image. The wheel
   is hash-checked against the
   [stable lock](../../docker/tcad/requirements.lock). The test passes. DEVSIM HEAD's `src/` is
   unchanged since 2.11.1, so the difference lies in the build, not the source.
5. **gdb.** Run [`trap_fpe.py`](trap_fpe.py) under [gdb](https://sourceware.org/gdb/) in the
   GCC 13.3 image. It stops with `SIGFPE` at a `cvttpd2dq` instruction in CPython's
   `_Py_dg_dtoa` (float to string). The call chain is DEVSIM's `ObjectHolder::GetString`, then
   `dsGetArgs::GetArgs::processOptions`, then `dsCommand::getParameterCmd`.
6. **Compiler swap.** In the pinned GCC 14 dev image
   ([`docker/TCAD_DEV_IMAGE`](../../docker/TCAD_DEV_IMAGE)), the test passes and the trap never
   fires.

**The root cause is not established.** `FE_INVALID` is raised in CPython's `_Py_dg_dtoa`, which
DEVSIM's GCC 13.3 build calls through `PyObject_Str` while it processes the arguments of
`set_parameter`. DEVSIM's per-command FPE check (`FPECheck`, around each command in
`PythonCommands.cc`) then reports the flag. The PyPI build and the GCC 14 build do not take that
path. Why the GCC 13.3 code does was not found. Using GCC 14, as upstream does, avoids it.
