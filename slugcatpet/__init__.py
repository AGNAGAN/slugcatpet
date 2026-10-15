"""蛞蝓猫桌宠。"""

import os

# 限制 OpenBLAS 线程数，免得按 CPU 线程数预留大块内存
for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ.setdefault(_k, "1")
