# -*- coding: utf-8 -*-
"""tests 包初始化：把包根挂上 sys.path（幂等），保证 `import yinqing` 总能命中。

无论从包根起跑（python -m unittest discover）还是从别处引用本包，
测试文件的裸模块导入（yinqing/ai_bianjie/houtai_hexin）都能解析。
"""

import sys
from pathlib import Path

# 包根 = 本文件的上一级目录（houtai_hexin_python/）
_BAO_GEN = Path(__file__).resolve().parents[1]
# 幂等插入：已存在则跳过（重复插入会污染搜索路径顺序）
if str(_BAO_GEN) not in sys.path:
    sys.path.insert(0, str(_BAO_GEN))
