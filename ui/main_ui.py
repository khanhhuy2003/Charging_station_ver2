# main.py
import sys
from PyQt5 import QtWidgets, QtCore
from controller.main_controller import MainController

# Trong phần cuối file main.py (hoặc trong __init__ của MainController nếu dùng MVC)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainController()  # hoặc MainController()
    
    # Chạy fullscreen + ẩn thanh tiêu đề
    window.showFullScreen()
    window.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
    
    # (Tùy chọn) Ẩn con trỏ chuột khi không di chuyển (rất đẹp cho kiosk)
    window.setCursor(QtCore.Qt.BlankCursor)

    window.show()
    sys.exit(app.exec_())
