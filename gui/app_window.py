# import sys
# import numpy as np
# import os

# # 1. 导入 PyQt5 组件 (已修复：添加了 QProgressBar)
# from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
#                              QHBoxLayout, QLabel, QLineEdit, 
#                              QPushButton, QComboBox, QSizePolicy, 
#                              QProgressBar, QFrame, QSpacerItem)
# from PyQt5.QtCore import Qt, pyqtSlot
# from PyQt5.QtGui import QImage, QPixmap

# # 2. 导入自定义模块
# from .styles import MODERN_THEME
# from .worker import CarlaWorker

# # 3. 尝试导入图标库 (可选)
# try:
#     import qtawesome as qta
#     HAS_ICONS = True
# except ImportError:
#     HAS_ICONS = False
#     print("提示: 未安装 qtawesome，将不显示图标 (pip install qtawesome)")

# class MainWindow(QMainWindow):
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("CARLA OpenLane Data Collector")
#         self.resize(1280, 720) # 调整为适合宽屏的分辨率
        
#         # 应用样式表
#         self.setStyleSheet(MODERN_THEME)
        
#         self.worker = None
#         self.init_ui()

#     def init_ui(self):
#         # --- 主容器 ---
#         main_widget = QWidget()
#         self.setCentralWidget(main_widget)
        
#         # 外层布局：垂直布局 (Header + Body)
#         outer_layout = QVBoxLayout(main_widget)
#         outer_layout.setContentsMargins(25, 25, 25, 25)
#         outer_layout.setSpacing(20)

#         # =========================================
#         # 1. 顶部标题栏 (Header)
#         # =========================================
#         header_layout = QHBoxLayout()
        
#         # 模拟 Logo (可以用 Emoji 或者图片)
#         logo_label = QLabel("🚙") 
#         logo_label.setStyleSheet("font-size: 28px; background: transparent;")
        
#         title_label = QLabel("CARLA OpenLane Data Collector")
#         title_label.setObjectName("HeaderTitle") # 对应样式表中的字体设置
        
#         header_layout.addWidget(logo_label)
#         header_layout.addWidget(title_label)
#         header_layout.addStretch() # 把标题顶在左边
        
#         outer_layout.addLayout(header_layout)

#         # =========================================
#         # 2. 内容主体 (Split View: Left Panel | Right Video)
#         # =========================================
#         body_layout = QHBoxLayout()
#         body_layout.setSpacing(25)

#         # -----------------------------------
#         # A. 左侧控制面板 (Side Panel)
#         # -----------------------------------
#         side_panel = QWidget()
#         side_panel.setObjectName("SidePanel") # 对应样式表圆角背景
#         side_panel.setFixedWidth(340)       # 固定宽度，保持紧凑
        
#         side_layout = QVBoxLayout(side_panel)
#         side_layout.setContentsMargins(20, 25, 20, 25)
#         side_layout.setSpacing(15)

#         # -- Connection --
#         side_layout.addWidget(self.create_label("Host Connection:"))
#         conn_layout = QHBoxLayout()
#         self.ip_input = QLineEdit("127.0.0.1")
#         self.port_input = QLineEdit("2000")
#         self.setup_input_icon(self.ip_input, "fa5s.desktop")
#         self.setup_input_icon(self.port_input, "fa5s.plug")
        
#         conn_layout.addWidget(self.ip_input, 7)
#         conn_layout.addWidget(self.port_input, 3)
#         side_layout.addLayout(conn_layout)

#         # -- Map --
#         side_layout.addWidget(self.create_label("Map Selection:"))
#         self.map_combo = QComboBox()
#         self.map_combo.addItems(["Town10HD", "Town04", "Town05", "Town03", "Town01", "Town02"])
#         self.map_combo.setFixedHeight(40)
#         side_layout.addWidget(self.map_combo)

#         # -- Target Frames --
#         side_layout.addWidget(self.create_label("Target Frames:"))
#         self.frames_input = QLineEdit("3000")
#         self.frames_input.setPlaceholderText("e.g. 3000")
#         self.setup_input_icon(self.frames_input, "fa5s.camera")
#         self.frames_input.setFixedHeight(40)
#         side_layout.addWidget(self.frames_input)

#         # -- Segment Name --
#         side_layout.addWidget(self.create_label("Segment Name:"))
#         self.segment_input = QLineEdit("segment-0")
#         self.setup_input_icon(self.segment_input, "fa5s.folder")
#         self.segment_input.setFixedHeight(40)
#         side_layout.addWidget(self.segment_input)

#         # -- Dataset Split --
#         side_layout.addWidget(self.create_label("Dataset Split:"))
#         self.split_combo = QComboBox()
#         self.split_combo.addItems(["training", "validation"])
#         self.split_combo.setFixedHeight(40)
#         side_layout.addWidget(self.split_combo)

#         # 弹簧组件，将按钮顶到底部
#         side_layout.addStretch()

#         # -- Buttons --
#         self.start_btn = QPushButton("START COLLECTION")
#         self.start_btn.setObjectName("startBtn")
#         self.start_btn.setCursor(Qt.PointingHandCursor)
#         self.start_btn.clicked.connect(self.start_collection)
#         if HAS_ICONS:
#             self.start_btn.setIcon(qta.icon('fa5s.play', color='white'))
        
#         self.stop_btn = QPushButton("STOP")
#         self.stop_btn.setObjectName("stopButton")
#         self.stop_btn.setCursor(Qt.PointingHandCursor)
#         self.stop_btn.setEnabled(False)
#         self.stop_btn.clicked.connect(self.stop_collection)
        
#         side_layout.addWidget(self.start_btn)
#         side_layout.addWidget(self.stop_btn)

#         body_layout.addWidget(side_panel)

#         # -----------------------------------
#         # B. 右侧视频监控区 (Video Panel)
#         # -----------------------------------
#         video_layout = QVBoxLayout()
        
#         # 1. 视频显示区域 (使用黑色背景 QLabel)
#         self.image_label = QLabel()
#         self.image_label.setAlignment(Qt.AlignCenter)
#         self.image_label.setStyleSheet("""
#             QLabel {
#                 background-color: #000000;
#                 border-radius: 12px;
#                 border: 2px solid #282c34;
#             }
#         """)
#         self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#         self.set_placeholder_image() # 显示初始文字
#         video_layout.addWidget(self.image_label)

#         # 2. 状态栏容器 (包含状态字和进度条)
#         status_container = QWidget()
#         status_container.setStyleSheet("background-color: #282c34; border-radius: 8px;")
#         status_bar_layout = QVBoxLayout(status_container)
#         status_bar_layout.setContentsMargins(15, 10, 15, 10)

#         # 上排：状态文本 + 百分比
#         info_row = QHBoxLayout()
#         self.status_label = QLabel("Status: Idle")
#         self.status_label.setStyleSheet("color: #61afef; font-weight: bold; font-size: 14px;")
        
#         self.percent_label = QLabel("0%")
#         self.percent_label.setStyleSheet("color: #abb2bf; font-weight: bold;")
        
#         info_row.addWidget(self.status_label)
#         info_row.addStretch()
#         info_row.addWidget(self.percent_label)
        
#         # 下排：进度条
#         self.progress_bar = QProgressBar()
#         self.progress_bar.setValue(0)
#         self.progress_bar.setTextVisible(False) # 隐藏自带文字，追求极简
#         self.progress_bar.setFixedHeight(6)     # 细条风格
        
#         status_bar_layout.addLayout(info_row)
#         status_bar_layout.addWidget(self.progress_bar)

#         video_layout.addWidget(status_container)
        
#         body_layout.addLayout(video_layout, stretch=1) # 右侧占用剩余空间
#         outer_layout.addLayout(body_layout)

#     # --- 辅助 UI 函数 ---
#     def create_label(self, text):
#         lbl = QLabel(text)
#         # 稍微调暗一点的灰色文字
#         lbl.setStyleSheet("font-size: 13px; color: #8b949e; font-weight: 500;")
#         return lbl

#     def setup_input_icon(self, widget, icon_name):
#         if HAS_ICONS and isinstance(widget, QLineEdit):
#             # 在输入框左侧添加图标
#             action = widget.addAction(qta.icon(icon_name, color='#5c6370'), QLineEdit.LeadingPosition)

#     def set_placeholder_image(self):
#         self.image_label.setText("Waiting for camera stream...\n\nPlease click [START COLLECTION]")
#         self.image_label.setStyleSheet("background-color: #000; color: #666; font-size: 16px; border-radius: 12px;")

#     # --- 逻辑控制部分 ---

#     def start_collection(self):
#         # 获取用户输入
#         try:
#             frames_val = int(self.frames_input.text())
#             port_val = int(self.port_input.text())
#         except ValueError:
#             self.status_label.setText("Error: Invalid number format!")
#             return

#         config = {
#             'host': self.ip_input.text(),
#             'port': port_val,
#             'town': self.map_combo.currentText(),
#             'frames': frames_val,
#             'segment': self.segment_input.text(),
#             'split': self.split_combo.currentText(),
#             'tm_port': 8000,
#             'seed': 42,
#             'min_speed': 1.0,
#             'min_dist': 3.0
#         }

#         # 实例化后台线程
#         self.worker = CarlaWorker(config)
        
#         # 绑定信号
#         self.worker.image_signal.connect(self.update_image)
#         self.worker.progress_signal.connect(self.update_progress)
#         self.worker.status_signal.connect(self.update_status) # 专门处理文本状态
#         self.worker.finished_signal.connect(self.on_worker_finished)
        
#         # 启动
#         self.worker.start()
        
#         # UI 状态切换
#         self.start_btn.setEnabled(False)
#         self.stop_btn.setEnabled(True)
#         self.progress_bar.setValue(0)
#         self.percent_label.setText("0%")
#         self.image_label.setText("Connecting to CARLA...")
#         self.status_label.setText("Status: Initializing...")

#     def stop_collection(self):
#         if self.worker:
#             self.status_label.setText("Status: Stopping (Cleaning up)...")
#             self.worker.stop()
#             self.stop_btn.setEnabled(False) # 防止重复点击

#     def on_worker_finished(self):
#         self.start_btn.setEnabled(True)
#         self.stop_btn.setEnabled(False)
#         self.status_label.setText("Status: Idle (Finished)")
#         self.set_placeholder_image()
#         self.worker = None

#     def update_progress(self, val):
#         self.progress_bar.setValue(val)
#         self.percent_label.setText(f"{val}%")

#     @pyqtSlot(str)
#     def update_status(self, text):
#         self.status_label.setText(text)

#     @pyqtSlot(np.ndarray)
#     def update_image(self, cv_img):
#         """将 Worker 传来的 OpenCV 图像转换为 QPixmap 显示"""
#         try:
#             h, w, ch = cv_img.shape
#             bytes_per_line = ch * w 
            
#             # 假设 worker 已经转为 RGB 格式
#             qt_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
#             # 缩放以适应 Label 大小 (保持比例)
#             pixmap = QPixmap.fromImage(qt_img).scaled(
#                 self.image_label.width(), 
#                 self.image_label.height(), 
#                 Qt.KeepAspectRatio,
#                 Qt.SmoothTransformation
#             )
#             self.image_label.setPixmap(pixmap)
#         except Exception as e:
#             print(f"Image Error: {e}")
# gui/app_window.py
import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGridLayout, QLabel, QLineEdit, QPushButton, 
                             QComboBox, QGroupBox, QTextEdit, QProgressBar, 
                             QSpinBox, QTabWidget, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap

from .styles import DARK_THEME
from .worker import CarlaWorker
from .validation_worker import ValidationWorker  # 导入新 Worker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CARLA OpenLane Studio") # 名字升级一下
        self.resize(1280, 850)
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
    # Tab 1: 数据采集 (原有逻辑封装)
    # ==========================================
    def init_collection_ui(self):
        layout = QHBoxLayout(self.tab_collection)
        
        # --- 左侧控制面板 ---
        left_panel = QVBoxLayout()
        
        # Connection
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QGridLayout()
        self.ip_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("2000")
        conn_layout.addWidget(QLabel("Host IP:"), 0, 0); conn_layout.addWidget(self.ip_input, 0, 1)
        conn_layout.addWidget(QLabel("Port:"), 1, 0); conn_layout.addWidget(self.port_input, 1, 1)
        conn_group.setLayout(conn_layout)
        left_panel.addWidget(conn_group)

        # Environment
        env_group = QGroupBox("Environment")
        env_layout = QVBoxLayout()
        self.map_combo = QComboBox()
        self.map_combo.addItems(["Town10HD", "Town04", "Town05", "Town03"])
        env_layout.addWidget(QLabel("Map:"))
        env_layout.addWidget(self.map_combo)
        env_group.setLayout(env_layout)
        left_panel.addWidget(env_group)

        # Params
        param_group = QGroupBox("Collection Params")
        param_layout = QGridLayout()
        self.frames_spin = QSpinBox()
        self.frames_spin.setRange(100, 100000); self.frames_spin.setValue(3000); self.frames_spin.setSingleStep(100)
        self.segment_input = QLineEdit("segment-0")
        self.split_combo = QComboBox(); self.split_combo.addItems(["training", "validation"])
        param_layout.addWidget(QLabel("Target Frames:"), 0, 0); param_layout.addWidget(self.frames_spin, 0, 1)
        param_layout.addWidget(QLabel("Segment Name:"), 1, 0); param_layout.addWidget(self.segment_input, 1, 1)
        param_layout.addWidget(QLabel("Dataset Split:"), 2, 0); param_layout.addWidget(self.split_combo, 2, 1)
        param_group.setLayout(param_layout)
        left_panel.addWidget(param_group)

        # Buttons
        self.start_btn = QPushButton("START COLLECTION")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.clicked.connect(self.start_collection)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setMinimumHeight(40); self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_collection)
        left_panel.addWidget(self.start_btn)
        left_panel.addWidget(self.stop_btn)
        left_panel.addStretch()

        # --- 右侧显示区域 ---
        right_panel = QVBoxLayout()
        self.image_label = QLabel("Waiting for stream...")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000; border: 2px solid #333;")
        self.image_label.setMinimumSize(800, 450)
        
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("font-size: 16px; color: #00acc1; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)

        right_panel.addWidget(self.image_label, stretch=3)
        right_panel.addLayout(status_layout)
        right_panel.addWidget(self.progress_bar)
        right_panel.addWidget(self.log_text, stretch=1)

        layout.addLayout(left_panel, stretch=1)
        layout.addLayout(right_panel, stretch=3)

    # ==========================================
    # Tab 2: 批量验证 (新功能)
    # ==========================================
    def init_validation_ui(self):
        layout = QVBoxLayout(self.tab_validation)
        
        # 1. 顶部设置栏
        top_group = QGroupBox("Validation Configuration")
        top_layout = QGridLayout()
        
        # 输入路径
        self.val_path_input = QLineEdit()
        self.val_path_input.setPlaceholderText("Path to json folder (e.g. data/OpenLane/lane3d_1000/training/segment-0)")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_validation_folder)
        
        top_layout.addWidget(QLabel("Data Folder:"), 0, 0)
        top_layout.addWidget(self.val_path_input, 0, 1)
        top_layout.addWidget(btn_browse, 0, 2)
        
        # 参数
        self.val_samples = QSpinBox(); self.val_samples.setRange(0, 100000); self.val_samples.setValue(500)
        self.val_w = QSpinBox(); self.val_w.setRange(0, 4000); self.val_w.setValue(1920)
        self.val_h = QSpinBox(); self.val_h.setRange(0, 4000); self.val_h.setValue(1280)
        
        top_layout.addWidget(QLabel("Num Samples (0=All):"), 1, 0)
        top_layout.addWidget(self.val_samples, 1, 1)
        
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("W:"))
        res_layout.addWidget(self.val_w)
        res_layout.addWidget(QLabel("H:"))
        res_layout.addWidget(self.val_h)
        res_layout.addStretch()
        top_layout.addLayout(res_layout, 1, 2)

        top_group.setLayout(top_layout)
        layout.addWidget(top_group)
        
        # 2. 按钮
        btn_layout = QHBoxLayout()
        self.btn_start_val = QPushButton("RUN VALIDATION")
        self.btn_start_val.setMinimumHeight(45)
        self.btn_start_val.clicked.connect(self.start_validation)
        self.btn_stop_val = QPushButton("STOP")
        self.btn_stop_val.setObjectName("stopButton")
        self.btn_stop_val.setMinimumHeight(45)
        self.btn_stop_val.setEnabled(False)
        self.btn_stop_val.clicked.connect(self.stop_validation)
        
        btn_layout.addWidget(self.btn_start_val)
        btn_layout.addWidget(self.btn_stop_val)
        layout.addLayout(btn_layout)
        
        # 3. 进度与日志
        self.val_progress = QProgressBar()
        self.val_progress.setValue(0)
        layout.addWidget(self.val_progress)
        
        self.val_log = QTextEdit()
        self.val_log.setReadOnly(True)
        self.val_log.setStyleSheet("font-family: Consolas; font-size: 13px;")
        layout.addWidget(self.val_log)

    # ==========================================
    # Logic: Collection
    # ==========================================
    def log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def start_collection(self):
        config = {
            'host': self.ip_input.text(),
            'port': int(self.port_input.text()),
            'town': self.map_combo.currentText(),
            'frames': self.frames_spin.value(),
            'segment': self.segment_input.text(),
            'split': self.split_combo.currentText(),
            'tm_port': 8000,
            'seed': 42,
            'min_speed': 1.0,
            'min_dist': 3.0
        }
        self.collection_worker = CarlaWorker(config)
        self.collection_worker.log_signal.connect(self.log)
        self.collection_worker.image_signal.connect(self.update_image)
        self.collection_worker.progress_signal.connect(self.progress_bar.setValue)
        self.collection_worker.status_signal.connect(self.status_label.setText)
        self.collection_worker.finished_signal.connect(self.on_collection_finished)
        self.collection_worker.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)

    def stop_collection(self):
        if self.collection_worker:
            self.collection_worker.stop()

    def on_collection_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.collection_worker = None
        self.log("Collection thread exited.")

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        h, w, ch = cv_img.shape
        bytes_per_line = ch * w
        qt_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img).scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio)
        self.image_label.setPixmap(pixmap)

    # ==========================================
    # Logic: Validation
    # ==========================================
    def browse_validation_folder(self):
        # 核心修改：添加 options=options 强制使用 Qt 自绘窗口，从而继承黑色主题
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.ShowDirsOnly
        
        d = QFileDialog.getExistingDirectory(
            self, 
            "Select JSON Folder", 
            ".", 
            options=options
        )
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