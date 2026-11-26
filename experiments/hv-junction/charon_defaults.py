# SPDX-License-Identifier: Apache-2.0
"""Print the silicon defaults compiled into Charon and compare them with ionize.py.

    python charon_defaults.py            (Charon image; writes into the working directory)

Charon keeps its material defaults in charon::Material_Properties, inside libcharon.so;
no input-deck command prints them. The image ships the headers and g++, so this builds a
few lines of C++ that ask the library, and runs them.
"""

from __future__ import annotations

import subprocess
import sys

import ionize

PROPERTIES = {
    "vanOverstraeten Electron alow": ionize.AN,
    "vanOverstraeten Electron blow": ionize.BN,
    "vanOverstraeten Electron ahigh": ionize.AN,
    "vanOverstraeten Electron bhigh": ionize.BN,
    "vanOverstraeten Electron E0": ionize.E_SWITCH,
    "vanOverstraeten Hole alow": ionize.AP_LO,
    "vanOverstraeten Hole blow": ionize.BP_LO,
    "vanOverstraeten Hole ahigh": ionize.AP_HI,
    "vanOverstraeten Hole bhigh": ionize.BP_HI,
    "vanOverstraeten Hole E0": ionize.E_SWITCH,
    "Selberherr Electron a0": ionize.AN,
    "Selberherr Electron E0": ionize.BN,
    "Selberherr Electron delta": 1.0,
    "Selberherr Hole a0": ionize.AP_LO,
    "Selberherr Hole E0": ionize.BP_LO,
    "Selberherr Hole delta": 1.0,
    "Relative Permittivity": 11.7,
    "Electron Affinity": None,
}

SOURCE = """
#include <iostream>
#include <string>
#include "Charon_Material_Properties.hpp"
int main(int argc, char** argv) {
  charon::Material_Properties& m = charon::Material_Properties::getInstance();
  std::cout.precision(12);
  for (int k = 1; k < argc; ++k) {
    try { std::cout << argv[k] << "=" << m.getPropertyValue("Silicon", argv[k]) << std::endl; }
    catch (std::exception& e) { std::cout << argv[k] << "=missing" << std::endl; }
  }
  return 0;
}
"""


def charon_values(names):
    """{property: value or None} of Charon's material "Silicon"."""
    with open("charon_defaults.cpp", "w") as f:
        f.write(SOURCE)
    quiet = {"capture_output": True, "text": True, "check": True}
    flags = subprocess.run(["mpicxx", "--showme:compile"], **quiet)  # noqa: PLW1510
    subprocess.run(["g++", "-std=c++17", "-I/opt/charon/include", *flags.stdout.split(),
                    "charon_defaults.cpp", "-o", "charon_defaults.exe", "-L/opt/charon/lib",
                    "-lcharon", "-lteuchosparameterlist", "-lteuchoscore",
                    "-Wl,-rpath,/opt/charon/lib", "-Wl,--allow-shlib-undefined"],
                   check=True)  # fmt: skip
    r = subprocess.run(["./charon_defaults.exe", *names], **quiet)  # noqa: PLW1510
    out = {}
    for line in r.stdout.splitlines():
        name, _, value = line.partition("=")
        if name in names:
            out[name] = None if value == "missing" else float(value)
    return out


def main():
    got = charon_values(list(PROPERTIES))
    for name, want in PROPERTIES.items():
        value = got.get(name)
        note = "" if want is None else ("same as here" if value == want else f"here {want:g}")
        print(f"DEFAULT Silicon | {name} = {value} {note}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
