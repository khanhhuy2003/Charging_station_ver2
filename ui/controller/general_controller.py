# controller/general_controller.py
from PyQt5 import QtWidgets
from model.general_status_model import General_Status_Model
class GeneralController:
    def __init__(self, parent):
        self.parent = parent  # MainController
        self.model = parent.general_model
        self.ui = parent.ui

        model = General_Status_Model()

    def update_general_status(self):
        # Update model
        status = self.model.set_status_value()
        opmode = self.model.set_opmode_value()
        server = self.model.set_server_connect()
        wifi = self.model.set_wifi_value()

        # 2️⃣ Update UI - Status text & icon
        self.ui.status_value.setText(status.name)    
        self.ui.general_status_icon.setText(status.value) 

        self.ui.server_connect.setText(server.name)   
        self.ui.wifi_value.setText(wifi.name)   
    


        # Set color theo status
        if status.name in ["IDLE", "DONE"]:
            color = "#4CAF50"      # xanh lá
        elif status.name == "WAITING":
            color = "#FF9800"      # cam
        elif status.name == "BUSY":
            color = "#F44336"      # đỏ
        else:
            color = "#455A64"      # xám

        self.ui.status_value.setStyleSheet(
            f"border: none; border-radius: 0px; color: {color};"
        )

        # (OPTIONAL) Update UI khác nếu có
        # ví dụ:
        # self.ui.opmode_value.setText(opmode.name)
        # self.ui.server_value.setText(server.name)
        # self.ui.wifi_value.setText(wifi.name)