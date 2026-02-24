# controller/main_controller.py
from PyQt5 import QtWidgets, QtCore
from view.ui_gen.main_ui import Ui_MainWindow
from view.ui_gen.ui_setting import Ui_Dialog_setting
from model.pin_model import PinModel
from model.general_status_model import General_Status_Model
from controller.pin_controller import PinController
from controller.general_controller import GeneralController

class MainController(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Trạm Sạc Pin - VINMOTION")

        # Khởi tạo model
        self.pin_model = PinModel()
        self.general_model = General_Status_Model()

        # Khởi tạo các controller con
        self.pin_ctrl = PinController(self)
        self.general_ctrl = GeneralController(self)
        self.ui.no_pin_value.setText(str(self.pin_model.active_pin_count))

        # Timer update toàn bộ
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_all)
        self.timer.start(4000)

        # Kết nối sự kiện
        self.ui.button_setting.clicked.connect(self.open_setting_dialog)

        for i in range(1, 6):
            frame = getattr(self.ui, f"frame_pin_{i}")
            frame.mousePressEvent = lambda e, p=i: self.pin_ctrl.open_pin_detail(p)

            # Nút rút pin (theo tên mới của bạn: pushButton_1 đến pushButton_6)
            btn_name = f"replace_button_{i}" if i < 5 else "replace_button_5"
            if hasattr(self.ui, btn_name):
                btn = getattr(self.ui, btn_name)
                btn.clicked.connect(lambda _, p=i: self.pin_ctrl.remove_pin(p))

        # Update lần đầu
        self.update_all()
        self.update_rut_pin_buttons_visibility()

    def update_all(self):
        """Update toàn bộ: general status + pin (pin update gọi từ pin_ctrl)"""
        self.general_ctrl.update_general_status()
        # Nếu cần update tất cả pin cùng lúc, gọi:
        for pin in range(1, 6):
            self.pin_ctrl.update_pin_ui(pin)
            self.pin_model.update_pin(pin)
        self.ui.no_pin_value.setText(str(self.pin_model.active_pin_count))

    def update_rut_pin_buttons_visibility(self):
        """Ẩn/hiện nút rút pin theo mode"""
        visible = (self.pin_model.current_mode == "Manual")
        for i in range(1, 6):
            btn_name = f"replace_button_{i}" if i < 5 else "replace_button_5"
            if hasattr(self.ui, btn_name):
                getattr(self.ui, btn_name).setVisible(visible)

    def open_setting_dialog(self):
        """Mở dialog Setting và xử lý lưu cài đặt"""
        dialog = QtWidgets.QDialog(self)
        ui_setting = Ui_Dialog_setting()
        ui_setting.setupUi(dialog)

        if self.pin_model.current_mode == "Auto":
            ui_setting.checkBox.setChecked(True)
            ui_setting.checkBox_2.setChecked(False)
        else:
            ui_setting.checkBox.setChecked(False)
            ui_setting.checkBox_2.setChecked(True)

        def save_settings():
            if ui_setting.checkBox.isChecked():
                self.pin_model.current_mode = "Auto"
            elif ui_setting.checkBox_2.isChecked():
                self.pin_model.current_mode = "Manual"

            self.ui.mode_value.setText(self.pin_model.current_mode)
            self.update_rut_pin_buttons_visibility()

            ssid = ui_setting.lineEdit.text().strip()
            password = ui_setting.lineEdit_2.text().strip()
            if ssid:
                print(f"Đã lưu WiFi: SSID = {ssid}, Password = {password}")

            QtWidgets.QMessageBox.information(dialog, "Thành công", "Đã lưu cài đặt!")
            dialog.accept()

        ui_setting.pushButton.clicked.connect(save_settings)
        dialog.exec_()