from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
from typing import Dict, List, Optional

from scanner import FileInfo, DiffItem, scan_directory, compare_files


class ScanThread(QThread):
    progress = pyqtSignal(str)
    scan_complete = pyqtSignal(list)
    status_changed = pyqtSignal(str)

    def __init__(self, left_path: str, right_path: str, parent=None):
        super().__init__(parent)
        self.left_path = left_path
        self.right_path = right_path
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _is_cancelled(self) -> bool:
        return self._cancel

    def _progress_handler(self, current_path: str):
        self.progress.emit(current_path)

    def run(self):
        left_root = Path(self.left_path)
        right_root = Path(self.right_path)

        self._cancel = False

        self.status_changed.emit(f"正在扫描：{left_root} ...")
        left_files: Dict[str, FileInfo] = scan_directory(
            left_root,
            progress_callback=self._progress_handler,
            cancel_check=self._is_cancelled
        )

        if self._cancel:
            self.status_changed.emit("扫描已取消")
            self.scan_complete.emit([])
            return

        self.status_changed.emit(f"正在扫描：{right_root} ...")
        right_files: Dict[str, FileInfo] = scan_directory(
            right_root,
            progress_callback=self._progress_handler,
            cancel_check=self._is_cancelled
        )

        if self._cancel:
            self.status_changed.emit("扫描已取消")
            self.scan_complete.emit([])
            return

        self.status_changed.emit("正在对比差异 ...")
        diffs = compare_files(left_files, right_files)

        if self._cancel:
            self.status_changed.emit("扫描已取消")
            self.scan_complete.emit([])
            return

        self.status_changed.emit(f"扫描完成，共发现 {len(diffs)} 项差异")
        self.scan_complete.emit(diffs)
