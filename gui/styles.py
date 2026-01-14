# gui/styles.py

DARK_THEME = """
/* =======================================================
   全局基础 (恢复深色背景)
   ======================================================= */
QMainWindow {
    background-color: #1e1e1e;
}
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    color: #f0f0f0;
}
QDialog {
    background-color: #1e1e1e;
}

/* =======================================================
   Tab 页签 (让它看起来更高级)
   ======================================================= */
QTabWidget::pane { 
    border: 1px solid #3d3d3d; 
    background-color: #1e1e1e; /* 保持与背景一致 */
    top: -1px; 
}
QTabBar::tab {
    background: #252526;
    color: #888888;
    padding: 10px 25px;
    border: 1px solid #3d3d3d;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 4px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #1e1e1e; /* 选中后与主背景融合 */
    color: #00acc1;       /* 选中文字变青色 */
    border-bottom: 1px solid #1e1e1e; /* 去掉底部边框，实现融合效果 */
    border-top: 2px solid #00acc1;    /* 顶部高亮条 */
}
QTabBar::tab:hover {
    background: #333333;
    color: #cccccc;
}

/* =======================================================
   输入框与下拉框 (恢复原版风格)
   ======================================================= */
QLineEdit, QSpinBox {
    background-color: #2d2d2d;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px;
    color: #ffffff;
    selection-background-color: #00acc1;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #00acc1;
    background-color: #333333;
}

/* 下拉框修复 */
QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px;
    min-height: 25px;
    color: #ffffff;
}
QComboBox:on { border: 1px solid #00acc1; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: none;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    border: 1px solid #444444;
    color: #ffffff;
    selection-background-color: #00acc1;
}

/* =======================================================
   文件选择对话框 (针对 QFileDialog 内部控件)
   ======================================================= */
QTreeView, QListView {
    background-color: #252526;
    color: #f0f0f0;
    border: 1px solid #3d3d3d;
}
QTreeView::item:hover, QListView::item:hover {
    background: #333333;
}
QTreeView::item:selected, QListView::item:selected {
    background: #00acc1;
    color: white;
}

/* =======================================================
   分组框 (QGroupBox)
   ======================================================= */
QGroupBox {
    border: 1px solid #3d3d3d;
    border-radius: 6px;
    margin-top: 24px; /* 增加顶部间距给标题 */
    background-color: #252526; 
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: #00acc1; /* 青色标题 */
    font-weight: bold;
    background-color: #1e1e1e; /* 标题背景与主窗口一致 */
}

/* =======================================================
   按钮 (恢复扁平化深蓝风格)
   ======================================================= */
QPushButton {
    background-color: #0d47a1; /* 深蓝 */
    color: white;
    border: none;
    border-radius: 4px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 14px;
}
QPushButton:hover { background-color: #1565c0; }
QPushButton:pressed { background-color: #0a3b82; }
QPushButton:disabled {
    background-color: #333333;
    color: #777777;
}

/* 停止按钮 (深红) */
QPushButton#stopButton { background-color: #b71c1c; }
QPushButton#stopButton:hover { background-color: #d32f2f; }

/* =======================================================
   日志与进度条 (恢复终端风格)
   ======================================================= */
QTextEdit {
    background-color: #000000; /* 纯黑背景 */
    border: 1px solid #333333;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #00e676; /* 终端绿 */
    padding: 5px;
}

QProgressBar {
    border: 1px solid #444444;
    border-radius: 4px;
    text-align: center;
    background-color: #333333;
    color: white; 
    height: 20px;
}
QProgressBar::chunk {
    background-color: #00acc1; /* 青色进度 */
}

/* 滚动条美化 (防止出现突兀的白色滚动条) */
QScrollBar:vertical {
    border: none;
    background: #2d2d2d;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #555555;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""