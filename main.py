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
from sync_thread import SyncThread, SyncTask
from watch_thread import WatchThread


COLOR_LEFT_ONLY = QColor(255, 200, 200)
COLOR_RIGHT_ONLY = QColor(200, 200, 255)
COLOR_DIFF = QColor(255, 245, 180)
COLOR_IDENTICAL = QColor(220, 255, 220)

COLOR_SYNC_PENDING = QColor(240, 240, 240)
COLOR_SYNC_COPYING = QColor(255, 235, 150)
COLOR_SYNC_SYNCED = QColor(180, 240, 180)
COLOR_SYNC_FAILED = QColor(255, 160, 160)
COLOR_SYNC_SKIPPED = QColor(220, 220, 220)


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


def get_sync_status_text(status: str) -> str:
    mapping = {
        SyncTask.STATUS_PENDING: "待同步",
        SyncTask.STATUS_COPYING: "正在复制",
        SyncTask.STATUS_SYNCED: "已同步",
        SyncTask.STATUS_FAILED: "失败",
        SyncTask.STATUS_SKIPPED: "已跳过",
    }
    return mapping.get(status, status)


def get_color_for_sync_status(status: str) -> QColor:
    mapping = {
        SyncTask.STATUS_PENDING: COLOR_SYNC_PENDING,
        SyncTask.STATUS_COPYING: COLOR_SYNC_COPYING,
        SyncTask.STATUS_SYNCED: COLOR_SYNC_SYNCED,
        SyncTask.STATUS_FAILED: COLOR_SYNC_FAILED,
        SyncTask.STATUS_SKIPPED: COLOR_SYNC_SKIPPED,
    }
    return mapping.get(status, COLOR_SYNC_PENDING)


class MainWindow(QMainWindow):
    COL_STATUS = 0
    COL_REL_PATH = 1
    COL_LEFT_SIZE = 2
    COL_RIGHT_SIZE = 3
    COL_LEFT_TIME = 4
    COL_RIGHT_TIME = 5
    COL_FULL_PATH = 6
    COL_SYNC_STATUS = 7
    COL_SYNC_PROGRESS = 8

    def __init__(self):
        super().__init__()
        self.setWindowTitle("同步大师 (SyncMaster) - 专业文件夹对账与同步工具")
        self.setMinimumSize(1300, 800)
        self.scan_thread: ScanThread = None
        self.sync_thread: SyncThread = None
        self.watch_thread: WatchThread = None
        self.current_diffs: list = []
        self.sync_tasks: list = []
        self.diff_row_to_task: dict = {}
        self._pending_auto_sync_paths: list = None
        self._auto_sync_active: bool = False
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

        self.btn_cancel_scan = QPushButton("取消扫描")
        self.btn_cancel_scan.setMinimumHeight(38)
        self.btn_cancel_scan.setEnabled(False)
        self.btn_cancel_scan.setStyleSheet("""
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
        self.btn_cancel_scan.clicked.connect(self.cancel_scan)
        btn_row.addWidget(self.btn_cancel_scan)

        path_layout.addLayout(btn_row)
        main_layout.addWidget(path_group)

        sync_group = QGroupBox("单向镜像同步（左 → 右）")
        sync_layout = QVBoxLayout(sync_group)

        sync_info_row = QHBoxLayout()
        self.sync_info_label = QLabel("请先完成对账扫描，然后点击「开始同步」执行单向镜像（左→右）。")
        self.sync_info_label.setStyleSheet("color: #555;")
        sync_info_row.addWidget(self.sync_info_label)
        sync_info_row.addStretch()
        sync_layout.addLayout(sync_info_row)

        overall_row = QHBoxLayout()
        overall_label = QLabel("总进度：")
        overall_label.setStyleSheet("font-weight: bold;")
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setRange(0, 100)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setFormat("%v/%m (%p%)")
        self.overall_progress_bar.setMinimumHeight(26)

        self.overall_count_label = QLabel("待同步：0 个")
        self.overall_count_label.setStyleSheet("color: #555; margin-left: 12px;")

        overall_row.addWidget(overall_label)
        overall_row.addWidget(self.overall_progress_bar, stretch=1)
        overall_row.addWidget(self.overall_count_label)
        sync_layout.addLayout(overall_row)

        watch_row = QHBoxLayout()

        self.watch_status_label = QLabel("自动同步：未开启")
        self.watch_status_label.setStyleSheet("""
            padding: 6px 14px;
            border-radius: 4px;
            background-color: #e0e0e0;
            color: #555;
            font-weight: bold;
        """)
        watch_row.addWidget(self.watch_status_label)

        watch_row.addStretch()

        self.btn_start_watch = QPushButton("👁 开启自动同步监控")
        self.btn_start_watch.setMinimumHeight(36)
        self.btn_start_watch.setStyleSheet("""
            QPushButton {
                background-color: #138496;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 7px 22px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #17a2b8; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_start_watch.clicked.connect(self.start_watch)
        watch_row.addWidget(self.btn_start_watch)

        self.btn_stop_watch = QPushButton("⏸ 停止自动同步监控")
        self.btn_stop_watch.setMinimumHeight(36)
        self.btn_stop_watch.setEnabled(False)
        self.btn_stop_watch.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 7px 22px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #868e96; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_stop_watch.clicked.connect(self.stop_watch)
        watch_row.addWidget(self.btn_stop_watch)

        sync_layout.addLayout(watch_row)

        sync_btn_row = QHBoxLayout()
        sync_btn_row.addStretch()

        self.btn_start_sync = QPushButton("▶ 开始同步")
        self.btn_start_sync.setMinimumHeight(38)
        self.btn_start_sync.setEnabled(False)
        self.btn_start_sync.setStyleSheet("""
            QPushButton {
                background-color: #218838;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 28px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #2e9e47; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_start_sync.clicked.connect(self.start_sync)
        sync_btn_row.addWidget(self.btn_start_sync)

        self.btn_cancel_sync = QPushButton("⏹ 取消同步")
        self.btn_cancel_sync.setMinimumHeight(38)
        self.btn_cancel_sync.setEnabled(False)
        self.btn_cancel_sync.setStyleSheet("""
            QPushButton {
                background-color: #a94442;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 28px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #c25d5a; }
            QPushButton:disabled { background-color: #a0a0a0; }
        """)
        self.btn_cancel_sync.clicked.connect(self.cancel_sync)
        sync_btn_row.addWidget(self.btn_cancel_sync)

        sync_layout.addLayout(sync_btn_row)
        main_layout.addWidget(sync_group)

        legend_group = QGroupBox("图例说明")
        legend_layout = QHBoxLayout(legend_group)
        legend_layout.addWidget(self._legend_item(COLOR_LEFT_ONLY, "左侧独有"))
        legend_layout.addWidget(self._legend_item(COLOR_RIGHT_ONLY, "右侧独有"))
        legend_layout.addWidget(self._legend_item(COLOR_DIFF, "大小/时间不同"))
        legend_layout.addWidget(self._legend_item(COLOR_IDENTICAL, "完全相同"))
        legend_layout.addSpacing(20)
        legend_layout.addWidget(self._legend_item(COLOR_SYNC_PENDING, "待同步"))
        legend_layout.addWidget(self._legend_item(COLOR_SYNC_COPYING, "正在复制"))
        legend_layout.addWidget(self._legend_item(COLOR_SYNC_SYNCED, "已同步"))
        legend_layout.addWidget(self._legend_item(COLOR_SYNC_FAILED, "失败"))
        legend_layout.addStretch()
        main_layout.addWidget(legend_group)

        table_group = QGroupBox("差异列表 / 同步清单")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "差异状态", "相对路径", "左侧大小", "右侧大小",
            "左侧修改时间", "右侧修改时间", "完整路径",
            "同步状态", "文件进度"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 280)
        self.table.setColumnWidth(2, 95)
        self.table.setColumnWidth(3, 95)
        self.table.setColumnWidth(4, 145)
        self.table.setColumnWidth(5, 145)
        self.table.setColumnWidth(6, 200)
        self.table.setColumnWidth(7, 90)
        self.table.setColumnWidth(8, 180)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
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

        edit.textChanged.connect(self._on_path_changed)

        row.addWidget(edit, stretch=1)
        row.addWidget(btn)
        layout.addLayout(row)
        return frame

    def _on_path_changed(self):
        if self.watch_thread and self.watch_thread.isRunning():
            self._auto_sync_active = False
            self.watch_thread.stop()
            self.status_label.setText("路径已变更，自动同步监控已停止")

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

        if self.watch_thread and self.watch_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "停止自动监控",
                "执行手动对账扫描需要先停止自动同步监控。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self._auto_sync_active = False
            self.watch_thread.stop()
            self.btn_start_watch.setEnabled(False)
            self.btn_stop_watch.setEnabled(False)

        self._reset_sync_ui()
        self.table.setRowCount(0)
        self.current_diffs = []
        self.progress_bar.setVisible(True)
        self.btn_scan.setEnabled(False)
        self.btn_cancel_scan.setEnabled(True)
        self.btn_start_sync.setEnabled(False)

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
        self.btn_cancel_scan.setEnabled(False)
        self.current_diffs = diffs
        self._populate_table(diffs)

        if diffs:
            identical = sum(1 for d in diffs if d.status == DiffItem.STATUS_IDENTICAL)
            different = len(diffs) - identical
            pending_sync = sum(1 for d in diffs if d.status in (
                DiffItem.STATUS_LEFT_ONLY,
                DiffItem.STATUS_DIFF_SIZE,
                DiffItem.STATUS_DIFF_TIME,
                DiffItem.STATUS_DIFF_BOTH
            ))
            self.status_label.setText(
                f"扫描完成：共 {len(diffs)} 项，相同 {identical} 项，差异 {different} 项"
            )
            self.sync_info_label.setText(
                f"扫描完成：共 {len(diffs)} 项，待同步 {pending_sync} 项（左→右）。"
            )
            self.overall_count_label.setText(f"待同步：{pending_sync} 个")
            if pending_sync > 0:
                self.btn_start_sync.setEnabled(True)

    def _reset_sync_ui(self):
        self.sync_tasks = []
        self.diff_row_to_task = {}
        self.overall_progress_bar.setRange(0, 100)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setFormat("%v/%m (%p%)")
        self.overall_count_label.setText("待同步：0 个")
        self.sync_info_label.setText("请先完成对账扫描，然后点击「开始同步」执行单向镜像（左→右）。")

    def _populate_table(self, diffs: list):
        self.table.setRowCount(0)
        self.table.setRowCount(len(diffs))
        self.diff_row_to_task = {}
        task_idx = 0

        for row, diff in enumerate(diffs):
            bg_color = get_color_for_status(diff.status)

            status_item = QTableWidgetItem(get_status_text(diff.status))
            status_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_STATUS, status_item)

            path_item = QTableWidgetItem(diff.rel_path)
            path_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_REL_PATH, path_item)

            left_size = format_size(diff.left_file.size) if diff.left_file else "-"
            left_size_item = QTableWidgetItem(left_size)
            left_size_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_LEFT_SIZE, left_size_item)

            right_size = format_size(diff.right_file.size) if diff.right_file else "-"
            right_size_item = QTableWidgetItem(right_size)
            right_size_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_RIGHT_SIZE, right_size_item)

            left_time = format_time(diff.left_file.mtime) if diff.left_file else "-"
            left_time_item = QTableWidgetItem(left_time)
            left_time_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_LEFT_TIME, left_time_item)

            right_time = format_time(diff.right_file.mtime) if diff.right_file else "-"
            right_time_item = QTableWidgetItem(right_time)
            right_time_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_RIGHT_TIME, right_time_item)

            if diff.left_file:
                full_path = str(diff.left_file.path)
            elif diff.right_file:
                full_path = str(diff.right_file.path)
            else:
                full_path = ""
            full_item = QTableWidgetItem(full_path)
            full_item.setBackground(QBrush(bg_color))
            self.table.setItem(row, self.COL_FULL_PATH, full_item)

            needs_sync = diff.status in (
                DiffItem.STATUS_LEFT_ONLY,
                DiffItem.STATUS_DIFF_SIZE,
                DiffItem.STATUS_DIFF_TIME,
                DiffItem.STATUS_DIFF_BOTH
            )
            if needs_sync:
                sync_bg = COLOR_SYNC_PENDING
                sync_status_text = get_sync_status_text(SyncTask.STATUS_PENDING)
                self.diff_row_to_task[row] = task_idx
                task_idx += 1
            else:
                sync_bg = QColor(255, 255, 255)
                sync_status_text = "—"

            sync_status_item = QTableWidgetItem(sync_status_text)
            sync_status_item.setBackground(QBrush(sync_bg))
            sync_status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_SYNC_STATUS, sync_status_item)

            if needs_sync:
                file_bar = QProgressBar()
                file_bar.setRange(0, 100)
                file_bar.setValue(0)
                file_bar.setTextVisible(True)
                file_bar.setFormat("%p%")
                file_bar.setMaximumHeight(20)
                self.table.setCellWidget(row, self.COL_SYNC_PROGRESS, file_bar)
            else:
                no_bar = QLabel("—")
                no_bar.setAlignment(Qt.AlignCenter)
                no_bar.setStyleSheet("color: #999;")
                self.table.setCellWidget(row, self.COL_SYNC_PROGRESS, no_bar)

    def start_sync(self):
        left_path = self.left_edit.text().strip()
        right_path = self.right_edit.text().strip()

        if not self.current_diffs:
            QMessageBox.warning(self, "提示", "没有扫描结果，请先执行对账扫描")
            return

        pending_count = sum(1 for d in self.current_diffs if d.status in (
            DiffItem.STATUS_LEFT_ONLY,
            DiffItem.STATUS_DIFF_SIZE,
            DiffItem.STATUS_DIFF_TIME,
            DiffItem.STATUS_DIFF_BOTH
        ))
        if pending_count == 0:
            QMessageBox.information(self, "提示", "没有需要同步的文件")
            return

        reply = QMessageBox.question(
            self,
            "确认同步",
            f"即将执行单向镜像同步（左 → 右）。\n\n"
            f"源路径：{left_path}\n"
            f"目标路径：{right_path}\n\n"
            f"待同步文件数：{pending_count}\n\n"
            f"注意：目标路径下的同名文件将被覆盖，且不会删除右侧独有文件。\n\n"
            f"是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.btn_start_sync.setEnabled(False)
        self.btn_cancel_sync.setEnabled(True)
        self.btn_scan.setEnabled(False)

        self.sync_thread = SyncThread(left_path, right_path, self.current_diffs)
        self.sync_thread.task_list_ready.connect(self.on_sync_task_list_ready)
        self.sync_thread.file_started.connect(self.on_sync_file_started)
        self.sync_thread.file_progress.connect(self.on_sync_file_progress)
        self.sync_thread.file_finished.connect(self.on_sync_file_finished)
        self.sync_thread.overall_progress.connect(self.on_sync_overall_progress)
        self.sync_thread.sync_complete.connect(self.on_sync_complete)
        self.sync_thread.status_changed.connect(self.on_status_changed)
        self.sync_thread.start()

    def cancel_sync(self):
        if self.sync_thread and self.sync_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "确认取消",
                "确定要取消同步吗？已开始复制的文件将被中断。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.sync_thread.cancel()
                self.status_label.setText("正在取消同步 ...")

    def start_watch(self):
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

        if self.watch_thread and self.watch_thread.isRunning():
            return

        if not self.current_diffs:
            self.status_label.setText("首次启动监控，正在执行初始扫描 ...")
            self._auto_sync_active = True
            self.btn_start_watch.setEnabled(False)
            self.btn_stop_watch.setEnabled(True)
            self._update_watch_status_label("正在初始化...", "init")

            self._auto_sync_pending_start = True
            self.scan_thread = ScanThread(left_path, right_path)
            self.scan_thread.progress.connect(self.on_scan_progress)
            self.scan_thread.status_changed.connect(self.on_status_changed)
            self.scan_thread.scan_complete.connect(self._on_initial_scan_complete)
            self.scan_thread.start()
            return

        self._start_watch_internal(left_path)

    def _start_watch_internal(self, left_path: str):
        self._auto_sync_active = True
        self.watch_thread = WatchThread(left_path)
        self.watch_thread.changes_detected.connect(self.on_changes_detected)
        self.watch_thread.status_changed.connect(self.on_status_changed)
        self.watch_thread.watch_started.connect(self.on_watch_started)
        self.watch_thread.watch_stopped.connect(self.on_watch_stopped)
        self.watch_thread.start()

        self.btn_start_watch.setEnabled(False)
        self.btn_stop_watch.setEnabled(True)

    def _on_initial_scan_complete(self, diffs: list):
        self.progress_bar.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_cancel_scan.setEnabled(False)
        self.current_diffs = diffs
        self._populate_table(diffs)

        if diffs:
            identical = sum(1 for d in diffs if d.status == DiffItem.STATUS_IDENTICAL)
            different = len(diffs) - identical
            pending_sync = sum(1 for d in diffs if d.status in (
                DiffItem.STATUS_LEFT_ONLY,
                DiffItem.STATUS_DIFF_SIZE,
                DiffItem.STATUS_DIFF_TIME,
                DiffItem.STATUS_DIFF_BOTH
            ))
            self.sync_info_label.setText(
                f"初始扫描完成：共 {len(diffs)} 项，待同步 {pending_sync} 项（左→右）。"
            )
            self.overall_count_label.setText(f"待同步：{pending_sync} 个")
            if pending_sync > 0:
                self.btn_start_sync.setEnabled(True)

        left_path = self.left_edit.text().strip()
        self._start_watch_internal(left_path)

    def stop_watch(self):
        if not self.watch_thread or not self.watch_thread.isRunning():
            self._auto_sync_active = False
            self.btn_start_watch.setEnabled(True)
            self.btn_stop_watch.setEnabled(False)
            self._update_watch_status_label("未开启", "off")
            return

        reply = QMessageBox.question(
            self,
            "确认停止",
            "确定要停止自动同步监控吗？源目录的变化将不再自动同步。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._auto_sync_active = False
        self.watch_thread.stop()
        self.btn_start_watch.setEnabled(False)
        self.btn_stop_watch.setEnabled(False)

    def on_watch_started(self):
        self._update_watch_status_label("监控中", "active")

    def on_watch_stopped(self):
        self.btn_start_watch.setEnabled(True)
        self.btn_stop_watch.setEnabled(False)
        self._update_watch_status_label("未开启", "off")

    def _update_watch_status_label(self, text: str, state: str):
        full_text = f"自动同步：{text}"
        if state == "active":
            style = """
                padding: 6px 14px;
                border-radius: 4px;
                background-color: #d4edda;
                color: #155724;
                font-weight: bold;
                border: 1px solid #28a745;
            """
        elif state == "init":
            style = """
                padding: 6px 14px;
                border-radius: 4px;
                background-color: #fff3cd;
                color: #856404;
                font-weight: bold;
                border: 1px solid #ffc107;
            """
        elif state == "syncing":
            style = """
                padding: 6px 14px;
                border-radius: 4px;
                background-color: #cce5ff;
                color: #004085;
                font-weight: bold;
                border: 1px solid #007bff;
            """
        else:
            style = """
                padding: 6px 14px;
                border-radius: 4px;
                background-color: #e0e0e0;
                color: #555;
                font-weight: bold;
            """
        self.watch_status_label.setText(full_text)
        self.watch_status_label.setStyleSheet(style)

    def on_changes_detected(self, changed_paths: list):
        if not self._auto_sync_active:
            return

        self._pending_auto_sync_paths = changed_paths

        left_path = self.left_edit.text().strip()
        right_path = self.right_edit.text().strip()

        self.status_label.setText(
            f"检测到 {len(changed_paths)} 个文件变化，正在重新扫描差异 ..."
        )
        self._update_watch_status_label("同步中", "syncing")

        self.scan_thread = ScanThread(left_path, right_path)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.status_changed.connect(self.on_status_changed)
        self.scan_thread.scan_complete.connect(self._on_auto_scan_complete)
        self.scan_thread.start()

    def _on_auto_scan_complete(self, diffs: list):
        self.progress_bar.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_cancel_scan.setEnabled(False)
        self.current_diffs = diffs
        self._populate_table(diffs)

        pending_paths = self._pending_auto_sync_paths or []
        self._pending_auto_sync_paths = None

        if not pending_paths:
            self._update_watch_status_label("监控中", "active")
            return

        affected_diffs = [
            d for d in diffs if d.rel_path in pending_paths
        ]

        pending_sync = sum(1 for d in affected_diffs if d.status in (
            DiffItem.STATUS_LEFT_ONLY,
            DiffItem.STATUS_DIFF_SIZE,
            DiffItem.STATUS_DIFF_TIME,
            DiffItem.STATUS_DIFF_BOTH
        ))

        if pending_sync == 0:
            self.status_label.setText(
                f"扫描完成：监控的 {len(pending_paths)} 个文件无需同步"
            )
            self._update_watch_status_label("监控中", "active")
            return

        left_path = self.left_edit.text().strip()
        right_path = self.right_edit.text().strip()

        self.btn_start_sync.setEnabled(False)
        self.btn_cancel_sync.setEnabled(False)
        self.btn_scan.setEnabled(False)

        self.sync_thread = SyncThread(
            left_path, right_path, diffs,
            only_paths=pending_paths
        )
        self.sync_thread.task_list_ready.connect(self.on_sync_task_list_ready)
        self.sync_thread.file_started.connect(self.on_sync_file_started)
        self.sync_thread.file_progress.connect(self.on_sync_file_progress)
        self.sync_thread.file_finished.connect(self.on_sync_file_finished)
        self.sync_thread.overall_progress.connect(self.on_sync_overall_progress)
        self.sync_thread.sync_complete.connect(self._on_auto_sync_complete)
        self.sync_thread.status_changed.connect(self.on_status_changed)
        self.sync_thread.start()

    def _on_auto_sync_complete(self, synced: int, failed: int, skipped: int):
        self.btn_start_sync.setEnabled(True)
        self.btn_cancel_sync.setEnabled(False)
        self.btn_scan.setEnabled(True)

        total = synced + failed + skipped
        self.status_label.setText(
            f"自动同步完成：成功 {synced} / 失败 {failed} / 跳过 {skipped}（共 {total} 个）"
        )

        if self._auto_sync_active:
            self._update_watch_status_label("监控中", "active")

    def on_sync_task_list_ready(self, tasks: list):
        self.sync_tasks = tasks
        total = len(tasks)
        self.overall_progress_bar.setRange(0, total if total > 0 else 100)
        self.overall_progress_bar.setValue(0)
        self.overall_count_label.setText(f"待同步：{total} 个")

        task_to_diff_row = {v: k for k, v in self.diff_row_to_task.items()}

        for task in tasks:
            row = task_to_diff_row.get(task.index)
            if row is not None:
                sync_status_item = self.table.item(row, self.COL_SYNC_STATUS)
                if sync_status_item:
                    sync_status_item.setText(get_sync_status_text(SyncTask.STATUS_PENDING))
                    sync_status_item.setBackground(QBrush(COLOR_SYNC_PENDING))

    def on_sync_file_started(self, task_index: int):
        task_to_diff_row = {v: k for k, v in self.diff_row_to_task.items()}
        row = task_to_diff_row.get(task_index)
        if row is not None:
            sync_status_item = self.table.item(row, self.COL_SYNC_STATUS)
            if sync_status_item:
                sync_status_item.setText(get_sync_status_text(SyncTask.STATUS_COPYING))
                sync_status_item.setBackground(QBrush(COLOR_SYNC_COPYING))
                sync_status_item.setToolTip("正在复制文件 ...")

    def on_sync_file_progress(self, task_index: int, copied_bytes: int):
        task_to_diff_row = {v: k for k, v in self.diff_row_to_task.items()}
        row = task_to_diff_row.get(task_index)
        if row is not None:
            task = self.sync_tasks[task_index] if task_index < len(self.sync_tasks) else None
            file_bar = self.table.cellWidget(row, self.COL_SYNC_PROGRESS)
            if file_bar and isinstance(file_bar, QProgressBar) and task:
                total = task.size
                if total > 0:
                    pct = int(copied_bytes / total * 100)
                else:
                    pct = 100
                file_bar.setRange(0, total)
                file_bar.setValue(copied_bytes)
                file_bar.setFormat(
                    f"{format_size(copied_bytes)}/{format_size(total)} ({pct}%)"
                )

    def on_sync_file_finished(self, task_index: int, status: str, error_msg: str):
        task_to_diff_row = {v: k for k, v in self.diff_row_to_task.items()}
        row = task_to_diff_row.get(task_index)
        if row is not None:
            sync_status_item = self.table.item(row, self.COL_SYNC_STATUS)
            if sync_status_item:
                sync_status_item.setText(get_sync_status_text(status))
                sync_status_item.setBackground(QBrush(get_color_for_sync_status(status)))
                if error_msg:
                    sync_status_item.setToolTip(error_msg)
                else:
                    sync_status_item.setToolTip("")

            task = self.sync_tasks[task_index] if task_index < len(self.sync_tasks) else None
            file_bar = self.table.cellWidget(row, self.COL_SYNC_PROGRESS)
            if file_bar and isinstance(file_bar, QProgressBar) and task:
                if status == SyncTask.STATUS_SYNCED:
                    file_bar.setValue(task.size)
                    file_bar.setFormat(f"✓ {format_size(task.size)} (100%)")
                elif status == SyncTask.STATUS_FAILED:
                    file_bar.setFormat(f"✗ 失败: {error_msg[:30]}")
                elif status == SyncTask.STATUS_SKIPPED:
                    file_bar.setFormat("已取消")

    def on_sync_overall_progress(self, current: int, total: int):
        self.overall_progress_bar.setRange(0, total if total > 0 else 100)
        self.overall_progress_bar.setValue(current)
        remaining = total - current
        self.overall_count_label.setText(
            f"进度：{current}/{total}，剩余：{remaining} 个"
        )

    def on_sync_complete(self, synced: int, failed: int, skipped: int):
        self.btn_start_sync.setEnabled(True)
        self.btn_cancel_sync.setEnabled(False)
        self.btn_scan.setEnabled(True)

        total = synced + failed + skipped
        msg = (
            f"同步任务结束。\n\n"
            f"总计：{total} 个\n"
            f"成功：{synced} 个\n"
            f"失败：{failed} 个\n"
            f"跳过/取消：{skipped} 个"
        )
        if failed > 0:
            QMessageBox.warning(self, "同步完成（有失败）", msg)
        elif skipped > 0:
            QMessageBox.information(self, "同步已取消", msg)
        else:
            QMessageBox.information(self, "同步完成", msg)

        self.overall_count_label.setText(
            f"完成：成功 {synced} / 失败 {failed} / 跳过 {skipped}"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
