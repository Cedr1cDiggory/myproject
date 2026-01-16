# gui/styles.py

DARK_THEME = """
/* =======================================================
   全局基础
   ======================================================= */
QMainWindow, QDialog, QFileDialog {
    background-color: #1e1e1e;
    color: #f0f0f0;
}
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #f0f0f0;
}

/* =======================================================
   【文件浏览/列表视图】 (QFileDialog)
   保持深灰色，区分层级
   ======================================================= */
QTreeView, QListView, QTableView {
    background-color: #252526;
    color: #f0f0f0;
    border: 1px solid #444444;
    selection-background-color: #00acc1;
    selection-color: #000000;
    outline: 0px;
    gridline-color: #333333;
}
QHeaderView::section {
    background-color: #333333;
    color: #f0f0f0;
    padding: 4px;
    border: 1px solid #444444;
}

/* =======================================================
   【修复1】下拉框 (QComboBox)
   本体深灰，但弹出列表(Popup)改为纯黑
   ======================================================= */
QComboBox {
    background-color: #333333;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    color: #ffffff;
    selection-background-color: #00acc1;
}
/* 下拉弹出的列表 -> 改为纯黑 */
QComboBox QAbstractItemView {
    background-color: #000000; /* 纯黑背景 */
    border: 1px solid #444444;
    color: #ffffff;
    selection-background-color: #00acc1;
    selection-color: #000000;
    outline: 0px;
}
/* 下拉箭头 */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid #555555;
    background-color: #333333;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #ffffff; 
    margin-right: 8px;
}

/* =======================================================
   【修复2】日志栏 (QTextEdit)
   背景改为纯黑，文字保持终端绿
   ======================================================= */
QTextEdit {
    background-color: #000000; /* 纯黑背景 */
    border: 1px solid #333333;
    color: #00e676;            /* 亮绿色文字 */
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
}
/* 滚动条 */
QScrollBar:vertical {
    border: none;
    background: #1e1e1e;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #555555;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

/* =======================================================
   按钮 (QPushButton)
   ======================================================= */
QPushButton {
    background-color: #1E88E5;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover { background-color: #42A5F5; }
QPushButton:pressed { background-color: #1565C0; }
QPushButton:disabled {
    background-color: #424242;
    color: #757575;
}
QPushButton#stopButton { background-color: #D32F2F; }
QPushButton#stopButton:hover { background-color: #E57373; }
QPushButton#stopButton:disabled { background-color: #424242; }

/* =======================================================
   其他控件
   ======================================================= */
QLineEdit, QSpinBox {
    background-color: #333333;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #26C6DA;
}

QGroupBox {
    border: 1px solid #444444;
    border-radius: 6px;
    margin-top: 22px; 
    background-color: #252526; 
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: #26C6DA; 
}

QTabWidget::pane { border: 1px solid #3d3d3d; }
QTabBar::tab {
    background: #252526;
    color: #888888;
    padding: 8px 20px;
    border: 1px solid #3d3d3d;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #1e1e1e; 
    color: #26C6DA;       
    border-top: 2px solid #26C6DA;   
}
"""