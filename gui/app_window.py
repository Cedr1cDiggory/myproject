# gui/app_window.py
import sys
import os
import numpy as np
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGridLayout, QLabel, QLineEdit, QPushButton, 
                             QComboBox, QGroupBox, QTextEdit, QProgressBar, 
                             QSpinBox, QTabWidget, QFileDialog, QMessageBox,
                             QSpacerItem, QSizePolicy) # 添加了 Spacer
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap

from .styles import DARK_THEME
from .worker import CarlaWorker
from .validation_worker import ValidationWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CARLA OpenLane Studio")
        self.resize(1360, 900) # 稍微加宽一点以容纳更多参数
        self.setStyleSheet(DARK_THEME)

        self.collection_worker = None
        self.validation_worker = None
        
        self.init_ui()

    def init_ui(self):
        # 主容器使用 QTabWidget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 创建两个标签页
        self.tab_collection = QWidget()
        self.tab_validation = QWidget()

        self.tabs.addTab(self.tab_collection, "Data Collection")
        self.tabs.addTab(self.tab_validation, "Batch Validation")

        # 初始化各个页面
        self.init_collection_ui()
        self.init_validation_ui()

    # ==========================================
    # Tab 1: 数据采集 (功能增强版)
    # ==========================================
    def init_collection_ui(self):
        layout = QHBoxLayout(self.tab_collection)
        
        # --- 左侧控制面板 (Scrollable 或者紧凑布局) ---
        # 为了防止屏幕小显示不下，这里使用紧凑布局
        left_panel = QVBoxLayout()
        left_panel.setSpacing(15) # 稍微拉开一点间距
        
        # 1. Connection Group
        conn_group = QGroupBox("Connection")
        conn_layout = QGridLayout()
        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("2000")
        conn_layout.addWidget(QLabel("IP:"), 0, 0); conn_layout.addWidget(self.ip_input, 0, 1)
        conn_layout.addWidget(QLabel("Port:"), 1, 0); conn_layout.addWidget(self.port_input, 1, 1)
        conn_group.setLayout(conn_layout)
        left_panel.addWidget(conn_group)

        # 2. Map & Basic Settings
        basic_group = QGroupBox("Basic Settings")
        basic_layout = QGridLayout()
        
        self.map_combo = QComboBox()
        self.map_combo.addItems(["Town10HD", "Town04", "Town05", "Town03", "Town01", "Town02"])
        
        self.split_combo = QComboBox()
        self.split_combo.addItems(["training", "validation"])
        
        self.segment_input = QLineEdit("segment-0")
        self.segment_input.setPlaceholderText("Folder Name")
        
        basic_layout.addWidget(QLabel("Map:"), 0, 0); basic_layout.addWidget(self.map_combo, 0, 1)
        basic_layout.addWidget(QLabel("Split:"), 1, 0); basic_layout.addWidget(self.split_combo, 1, 1)
        basic_layout.addWidget(QLabel("Name:"), 2, 0); basic_layout.addWidget(self.segment_input, 2, 1)
        basic_group.setLayout(basic_layout)
        left_panel.addWidget(basic_group)

        # 3. Simulation Config (新增：天气、交通、障碍物)
        sim_group = QGroupBox("Simulation Config")
        sim_layout = QGridLayout()
        
        # 天气选择 (对应 WeatherManager)
        self.weather_combo = QComboBox()
        # 对应你后端 weather_manager.py 的逻辑
        self.weather_combo.addItems([
            "Random (Default)",    # 随机
            "Clear Noon",          # 晴天
            "Overcast",            # 阴天
            "Rain",                # 下雨
            "LongTail: Glare",     # 长尾：眩光
            "LongTail: Heavy Fog", # 长尾：团雾
            "LongTail: After Rain" # 长尾：雨后
        ])
        
        # 车辆数量 (对应 TrafficManager)
        self.vehicle_spin = QSpinBox()
        self.vehicle_spin.setRange(0, 200); self.vehicle_spin.setValue(50)
        
        # 行人数量 (对应 TrafficManager)
        self.walker_spin = QSpinBox()
        self.walker_spin.setRange(0, 200); self.walker_spin.setValue(20)
        
        # 障碍物数量 (对应 SceneManager)
        self.props_spin = QSpinBox()
        self.props_spin.setRange(0, 100); self.props_spin.setValue(10)
        
        # 布局
        sim_layout.addWidget(QLabel("Weather:"), 0, 0)
        sim_layout.addWidget(self.weather_combo, 0, 1)
        
        sim_layout.addWidget(QLabel("Vehicles:"), 1, 0)
        sim_layout.addWidget(self.vehicle_spin, 1, 1)
        
        sim_layout.addWidget(QLabel("Walkers:"), 2, 0)
        sim_layout.addWidget(self.walker_spin, 2, 1)

        sim_layout.addWidget(QLabel("Obstacles:"), 3, 0)
        sim_layout.addWidget(self.props_spin, 3, 1)
        
        sim_group.setLayout(sim_layout)
        left_panel.addWidget(sim_group)

        # 4. Capture Params
        cap_group = QGroupBox("Capture Params")
        cap_layout = QHBoxLayout()
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(100, 100000)
        self.frames_spin.setValue(3000)
        self.frames_spin.setSingleStep(100)
        self.frames_spin.setSuffix(" frames")
        cap_layout.addWidget(QLabel("Target:"))
        cap_layout.addWidget(self.frames_spin)
        cap_group.setLayout(cap_layout)
        left_panel.addWidget(cap_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("START")
        self.start_btn.setMinimumHeight(45)
        self.start_btn.clicked.connect(self.start_collection)
        
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setMinimumHeight(45)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_collection)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        
        left_panel.addStretch() # 弹簧
        left_panel.addLayout(btn_layout)

        # --- 右侧显示区域 ---
        right_panel = QVBoxLayout()
        
        # 视频区域
        self.image_label = QLabel("Waiting for CARLA stream...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000; border: 2px solid #333; border-radius: 4px;")
        self.image_label.setMinimumSize(800, 450)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 状态栏
        status_container = QWidget()
        status_container.setStyleSheet("background-color: #252526; border-radius: 4px;")
        status_layout = QHBoxLayout(status_container)
        
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("font-size: 14px; color: #00acc1; font-weight: bold;")
        
        self.percent_label = QLabel("0%")
        self.percent_label.setStyleSheet("color: #888;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.percent_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("System logs will appear here...")

        right_panel.addWidget(self.image_label, stretch=4)
        right_panel.addWidget(status_container)
        right_panel.addWidget(self.progress_bar)
        right_panel.addWidget(self.log_text, stretch=1)

        # 组合左右
        # 左侧固定宽度，右侧自适应
        left_container = QWidget()
        left_container.setLayout(left_panel)
        left_container.setFixedWidth(320) # 稍微加宽以容纳文字
        
        layout.addWidget(left_container)
        layout.addLayout(right_panel)

    # ==========================================
    # Tab 2: 批量验证 (保持不变，仅适配样式)
    # ==========================================
    def init_validation_ui(self):
        layout = QVBoxLayout(self.tab_validation)
        layout.setContentsMargins(30, 30, 30, 30) # 增加内边距
        
        # 1. 顶部设置栏
        top_group = QGroupBox("Validation Configuration")
        top_layout = QGridLayout()
        top_layout.setVerticalSpacing(15)
        
        # 输入路径
        self.val_path_input = QLineEdit()
        self.val_path_input.setPlaceholderText("Path to dataset folder (e.g. data/OpenLane/lane3d_1000/training/segment-0)")
        btn_browse = QPushButton("Browse")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self.browse_validation_folder)
        
        top_layout.addWidget(QLabel("Data Folder:"), 0, 0)
        top_layout.addWidget(self.val_path_input, 0, 1)
        top_layout.addWidget(btn_browse, 0, 2)
        
        # 参数
        self.val_samples = QSpinBox(); self.val_samples.setRange(0, 100000); self.val_samples.setValue(500)
        self.val_w = QSpinBox(); self.val_w.setRange(0, 4000); self.val_w.setValue(1920)
        self.val_h = QSpinBox(); self.val_h.setRange(0, 4000); self.val_h.setValue(1280)
        
        top_layout.addWidget(QLabel("Samples (0=All):"), 1, 0)
        top_layout.addWidget(self.val_samples, 1, 1)
        
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Resolution W:"))
        res_layout.addWidget(self.val_w)
        res_layout.addWidget(QLabel("H:"))
        res_layout.addWidget(self.val_h)
        res_layout.addStretch()
        top_layout.addLayout(res_layout, 1, 2)

        top_group.setLayout(top_layout)
        layout.addWidget(top_group)
        
        # 2. 按钮区
        btn_layout = QHBoxLayout()
        self.btn_start_val = QPushButton("RUN VALIDATION")
        self.btn_start_val.setMinimumHeight(50)
        self.btn_start_val.clicked.connect(self.start_validation)
        
        self.btn_stop_val = QPushButton("STOP")
        self.btn_stop_val.setObjectName("stopButton")
        self.btn_stop_val.setMinimumHeight(50)
        self.btn_stop_val.setEnabled(False)
        self.btn_stop_val.clicked.connect(self.stop_validation)
        
        btn_layout.addWidget(self.btn_start_val)
        btn_layout.addWidget(self.btn_stop_val)
        layout.addLayout(btn_layout)
        
        # 3. 进度与日志
        layout.addWidget(QLabel("Progress:"))
        self.val_progress = QProgressBar()
        self.val_progress.setValue(0)
        self.val_progress.setFixedHeight(10)
        layout.addWidget(self.val_progress)
        
        layout.addWidget(QLabel("Logs:"))
        self.val_log = QTextEdit()
        self.val_log.setReadOnly(True)
        layout.addWidget(self.val_log)

    # ==========================================
    # Logic: Collection
    # ==========================================
    def log(self, msg):
        self.log_text.append(msg)
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def start_collection(self):
        # 1. 获取基础参数
        try:
            frames_val = self.frames_spin.value()
            port_val = int(self.port_input.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid Port Number!")
            return

        # 2. 获取新的仿真参数
        weather_mode = self.weather_combo.currentText()
        # 简单映射一下 ComboBox 文本到 config 字符串 (方便后端处理)
        if "Random" in weather_mode: w_val = "random"
        elif "Clear" in weather_mode: w_val = "clear"
        elif "Overcast" in weather_mode: w_val = "overcast"
        elif "Rain" in weather_mode: w_val = "rain"
        elif "Glare" in weather_mode: w_val = "longtail_glare"
        elif "Fog" in weather_mode: w_val = "longtail_fog"
        elif "After Rain" in weather_mode: w_val = "longtail_storm"
        else: w_val = "random"

        config = {
            'host': self.ip_input.text(),
            'port': port_val,
            'town': self.map_combo.currentText(),
            'frames': frames_val,
            'segment': self.segment_input.text(),
            'split': self.split_combo.currentText(),
            'tm_port': 8000,
            
            # --- 新增配置传递给后端 ---
            'num_vehicles': self.vehicle_spin.value(),
            'num_walkers': self.walker_spin.value(),
            'num_props': self.props_spin.value(),
            'weather_mode': w_val,
            
            # 固定参数
            'seed': 42,
            'min_speed': 1.0,
            'min_dist': 3.0
        }
        
        self.collection_worker = CarlaWorker(config)
        
        # 信号绑定
        self.collection_worker.log_signal.connect(self.log)
        self.collection_worker.image_signal.connect(self.update_image)
        self.collection_worker.progress_signal.connect(self.update_progress)
        self.collection_worker.status_signal.connect(self.status_label.setText)
        self.collection_worker.finished_signal.connect(self.on_collection_finished)
        
        self.collection_worker.start()
        
        # UI 状态更新
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")
        self.log(">>> Starting Collection Thread >>>")

    def update_progress(self, val):
        self.progress_bar.setValue(val)
        self.percent_label.setText(f"{val}%")

    def stop_collection(self):
        if self.collection_worker:
            self.collection_worker.stop()
            self.log("Stopping...")

    def on_collection_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.collection_worker = None
        self.status_label.setText("Status: Idle")
        self.log("Collection thread exited.")

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        try:
            h, w, ch = cv_img.shape
            bytes_per_line = ch * w
            qt_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            # 保持比例缩放
            pixmap = QPixmap.fromImage(qt_img).scaled(
                self.image_label.width(), 
                self.image_label.height(), 
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(pixmap)
        except Exception:
            pass

    # ==========================================
    # Logic: Validation
    # ==========================================
    def browse_validation_folder(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.ShowDirsOnly
        d = QFileDialog.getExistingDirectory(self, "Select JSON Folder", ".", options=options)
        if d:
            self.val_path_input.setText(d)

    def log_val(self, msg):
        self.val_log.append(msg)
        self.val_log.verticalScrollBar().setValue(self.val_log.verticalScrollBar().maximum())

    def start_validation(self):
        path = self.val_path_input.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Invalid folder path!")
            return
            
        out_csv = os.path.join(path, "validation_report.csv")
        
        self.validation_worker = ValidationWorker(
            input_dir=path,
            num_samples=self.val_samples.value(),
            img_w=self.val_w.value(),
            img_h=self.val_h.value(),
            out_csv=out_csv
        )
        self.validation_worker.log_signal.connect(self.log_val)
        self.validation_worker.progress_signal.connect(self.val_progress.setValue)
        self.validation_worker.finished_signal.connect(self.on_val_finished)
        
        self.validation_worker.start()
        self.btn_start_val.setEnabled(False)
        self.btn_stop_val.setEnabled(True)
        self.val_log.clear()
        self.log_val(">>> Starting Validation >>>")

    def stop_validation(self):
        if self.validation_worker:
            self.validation_worker.stop()
            self.log_val("Stopping...")

    def on_val_finished(self, msg):
        self.btn_start_val.setEnabled(True)
        self.btn_stop_val.setEnabled(False)
        self.validation_worker = None
        self.log_val(f"Finished: {msg}")