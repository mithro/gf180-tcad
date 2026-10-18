# Reproduce

How to rerun everything in this project. Every simulator invocation runs inside
a pinned container image through a resource-limited sandbox, so a result can be
regenerated on another machine and compared byte for byte.

Results are produced as files with fixed formatting (shortest round-trip
floats, `\n` line endings, `.` decimal separator, sorted JSON keys, UTF-8, no
timestamps, hostnames or absolute host paths), and the documentation will
be generated from those files, so the pages will never show numbers that cannot
be reproduced.

**Not yet available:** one-command reproduction (`make reproduce`) and running
a single device. Both arrive in later tasks.

```{toctree}
:maxdepth: 1

sandbox
image
```
