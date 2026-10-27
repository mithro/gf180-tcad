# SPDX-License-Identifier: Apache-2.0
"""The 3D renders of the simulated processes (design spec §10.1).

:mod:`gf180tcad.render.manifest` holds the render manifest: for every quantity a render
draws, the committed file it comes from, the selector inside that file, the unit, the value
and the scale factor, and for every derived quantity the formula of :mod:`gf180tcad.derive`
and its inputs. The package never imports Blender's ``bpy``.
"""
