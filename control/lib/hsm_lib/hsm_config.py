"""
hsm_config.py
Cấu hình cho Hierarchical State Machine (HSM) library
"""

USE_KCONFIG = False

if USE_KCONFIG:

    MAX_DEPTH = 8       # placeholder
    HISTORY = True
else:

    MAX_DEPTH = 8
    HISTORY = True