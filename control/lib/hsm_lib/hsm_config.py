"""
hsm_config.py
Cấu hình cho Hierarchical State Machine (HSM) library
"""

# Nếu bạn dùng một hệ thống config kiểu Kconfig (như ESP-IDF), có thể bật ở đây
# Hiện tại để False để dùng cấu hình thủ công
USE_KCONFIG = False

if USE_KCONFIG:
    # Giả sử bạn có cách đọc từ config hệ thống (ví dụ import sdkconfig)
    # Ở đây để trống vì Python thường không có sdkconfig
    MAX_DEPTH = 8       # placeholder
    HISTORY = True
else:
    """
    Cấu hình thủ công (manual configuration)
    """
    # Số mức tối đa của state hierarchy (2–16)
    # Mỗi mức dùng thêm stack ~ vài byte khi transition
    MAX_DEPTH = 8

    # Bật/tắt tính năng history (transition về state trước đó)
    # Thêm 1 tham chiếu (state pointer) vào instance HSM
    HISTORY = True