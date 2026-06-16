import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QBrush, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QStatusBar, QMessageBox, QProgressBar, QSplitter, QFrame,
    QGroupBox
)

from scanner import DiffItem, FileInfo
from scan_thread import ScanThread


COLOR_LEFT_ONLY = QColor(255, 200, 200)
COLOR_RIGHT_ONLY = QColor(200, 200, 255)
COLOR_DIFF = QColor(255, 245, 180)
COLOR_IDENTICAL = QColor(220, 255, 220)


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


def format_time(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def get_status_text(status: str) -> str:
    mapping = {
        DiffItem.STATUS_LEFT_ONLY: "左侧独有",
        DiffItem.STATUS_RIGHT_ONLY: "右侧独有",
        DiffItem.STATUS_DIFF_SIZE: "大小不同",
        DiffItem.STATUS_DIFF_TIME: "时间不同",
        DiffItem.STATUS_DIFF_BOTH: "大小+时间不同",
        DiffItem.STATUS_IDENTICAL: "完全相同",
    }
    return mapping.get(status, status)


def get_color_for_status(status: str) -> QColor:
    if status == DiffItem.STATUS_LEFT_ONLY:
        return COLOR_LEFT_ONLY
    elif status == DiffItem.STATUS_RIGHT_ONLY:
        return COLOR_RIGHT_ONLY
    elif status in (DiffItem.STATUS_DIFF_SIZE, DiffItem.STATUS_DIFF_TIME, DiffItem.STATUS_DIFF_BOTH):
        return COLOR_DIFF
    else:
        return COLOR_IDENTICAL


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("同步大师 (SyncMaster) - 专业文件夹对账与同步工具")
        self.setMinimumSize(1200, 700)
        self.scan_thread: ScanThread = None
        self.current_diffs: list = []
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 8)

        title = QLabel("同步大师 (SyncMaster)")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #2c5aa0; margin-bottom: 6px;")
        main_layout.addWidget(title)

        subtitle = QLabel("毫秒级差异对账 · 本地硬盘 / NAS / U 盘 增量备份助手")
        subtitle.setStyleSheet("color: #666; margin-bottom: 6px;")
        main_layout.addWidget(subtitle)

        path_group = QGroupBox("路径选择")
        path_layout = QVBoxLayout(path_group)

        left_box = self._build_path_panel("源路径（左侧）", "left")
        right_box = self._build_path_panel("目标路径（右侧）", "right")
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setSizes([1, 1])
        path_layout.addWidget(splitter)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_scan = QPushButton("开始对账扫描")
        self.btn_scan.setMinimumHeight(38)
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background-color: #2c5aa0;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #3d6eb5; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_scan.clicked.connect(self.start_scan)
        btn_row.addWidget(self.btn_scan)

        self.btn_cancel = QPushButton("取消扫描")
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #a94442;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #c25d5a; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_cancel.clicked.connect(self.cancel_scan)
        btn_row.addWidget(self.btn_cancel)

        path_layout.addLayout(btn_row)
        main_layout.addWidget(path_group)

        legend_group = QGroupBox("图例说明")
        legend_layout = QHBoxLayout(legend_group)
        legend_layout.addWidget(self._legend_item(COLOR_LEFT_ONLY, "左侧独有"))
        legend_layout.addWidget(self._legend_item(COLOR_RIGHT_ONLY, "右侧独有"))
        legend_layout.addWidget(self._legend_item(COLOR_DIFF, "大小/时间不同"))
        legend_layout.addWidget(self._legend_item(COLOR_IDENTICAL, "完全相同"))
        legend_layout.addStretch()
        main_layout.addWidget(legend_group)

        table_group = QGroupBox("差异列表")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "状态", "相对路径", "左侧大小", "右侧大小",
            "左侧修改时间", "右侧修改时间", "完整路径"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 150)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table)

        main_layout.addWidget(table_group, stretch=1)

        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.statusbar.addWidget(self.status_label, stretch=1)
        self.statusbar.addPermanentWidget(self.progress_bar)

    def _build_path_panel(self, label_text: str, side: str) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(label)

        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setPlaceholderText(f"选择{label_text}目录 ...")
        btn = QPushButton("浏览...")
        btn.setFixedWidth(80)

        if side == "left":
            self.left_edit = edit
            self.left_btn = btn
            btn.clicked.connect(lambda: self._browse(self.left_edit))
        else:
            self.right_edit = edit
            self.right_btn = btn
            btn.clicked.connect(lambda: self._browse(self.right_edit))

        row.addWidget(edit, stretch=1)
        row.addWidget(btn)
        layout.addLayout(row)
        return frame

    def _legend_item(self, color: QColor, text: str) -> QWidget:
        box = QHBoxLayout()
        swatch = QLabel()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888; border-radius: 3px;")
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #444;")
        box.addWidget(swatch)
        box.addWidget(lbl)
        wrapper = QWidget()
        wrapper.setLayout(box)
        return wrapper

    def _browse(self, edit: QLineEdit):
        start_dir = edit.text() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", start_dir)
        if path:
            edit.setText(path)

    def start_scan(self):
        left_path = self.left_edit.text().strip()
        right_path = self.right_edit.text().strip()

        if not left_path or not right_path:
            QMessageBox.warning(self, "提示", "请先选择源路径和目标路径")
            return

        if not Path(left_path).is_dir():
            QMessageBox.warning(self, "提示", f"左侧路径不是有效目录：\n{left_path}")
            return

        if not Path(right_path).is_dir():
            QMessageBox.warning(self, "提示", f"右侧路径不是有效目录：\n{right_path}")
            return

        if left_path == right_path:
            QMessageBox.warning(self, "提示", "源路径和目标路径不能相同")
            return

        self.table.setRowCount(0)
        self.current_diffs = []
        self.progress_bar.setVisible(True)
        self.btn_scan.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self.scan_thread = ScanThread(left_path, right_path)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.status_changed.connect(self.on_status_changed)
        self.scan_thread.scan_complete.connect(self.on_scan_complete)
        self.scan_thread.start()

    def cancel_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.status_label.setText("正在取消扫描 ...")

    def on_scan_progress(self, current_path: str):
        self.status_label.setText(f"正在扫描：{current_path}")

    def on_status_changed(self, text: str):
        self.status_label.setText(text)

    def on_scan_complete(self, diffs: list):
        self.progress_bar.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.current_diffs = diffs
        self._populate_table(diffs)

        if diffs:
            identical = sum(1 for d in diffs if d.status == DiffItem.STATUS_IDENTICAL)
            different = len(diffs) - identical
            self.status_label.setText(
                f"扫描完成：共 {len(diffs)} 项，相同 {identical} 项，差异 {different} 项"
            )

    def _populate_table(self, diffs: list):
        self.table.setRowCount(0)
        self.table.setRowCount(len(diffs))

        for row, diff in enumerate(diffs):
            bg_color = get_color_for_status(diff.status)

            status_item = QTableWidgetItem(get_status_text(diff.status))
            status_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 0, status_item)

            path_item = QTableWidgetItem(diff.rel_path)
            path_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 1, path_item)

            left_size = format_size(diff.left_file.size) if diff.left_file else "-"
            left_size_item = QTableWidgetItem(left_size)
            left_size_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 2, left_size_item)

            right_size = format_size(diff.right_file.size) if diff.right_file else "-"
            right_size_item = QTableWidgetItem(right_size)
            right_size_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 3, right_size_item)

            left_time = format_time(diff.left_file.mtime) if diff.left_file else "-"
            left_time_item = QTableWidgetItem(left_time)
            left_time_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 4, left_time_item)

            right_time = format_time(diff.right_file.mtime) if diff.right_file else "-"
            right_time_item = QTableWidgetItem(right_time)
            right_time_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 5, right_time_item)

            if diff.left_file:
                full_path = str(diff.left_file.path)
            elif diff.right_file:
                full_path = str(diff.right_file.path)
            else:
                full_path = ""
            full_item = QTableWidgetItem(full_path)
            full_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, 6, full_item)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
