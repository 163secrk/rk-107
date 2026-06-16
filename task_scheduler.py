import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from profiles import SyncProfile
from scanner import DiffItem, FileInfo, scan_directory, compare_files
from sync_thread import SyncTask
from watch_thread import SyncEventTracker


@dataclass
class FailedFile:
    rel_path: str
    error_msg: str
    error_category: str


@dataclass
class SkippedFile:
    rel_path: str
    reason: str


@dataclass
class ProfileResult:
    profile_id: str
    profile_name: str
    source_path: str
    target_path: str
    started_at: str = ""
    finished_at: str = ""
    total_files: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    failed_files: List[FailedFile] = field(default_factory=list)
    skipped_files: List[SkippedFile] = field(default_factory=list)
    scan_total: int = 0
    scan_identical: int = 0
    scan_diff: int = 0
    scan_left_only: int = 0
    scan_right_only: int = 0


ERROR_CATEGORY_PERMISSION = "权限不足"
ERROR_CATEGORY_DISK_FULL = "磁盘空间不足"
ERROR_CATEGORY_FILE_IN_USE = "文件被占用"
ERROR_CATEGORY_NOT_FOUND = "文件不存在"
ERROR_CATEGORY_IO = "IO错误"
ERROR_CATEGORY_OTHER = "其他错误"


def categorize_error(error_msg: str) -> str:
    msg = error_msg.lower()
    if any(k in msg for k in ["permission", "access denied", "权限", "拒绝访问"]):
        return ERROR_CATEGORY_PERMISSION
    if any(k in msg for k in ["no space", "disk full", "enospc", "空间不足", "磁盘满"]):
        return ERROR_CATEGORY_DISK_FULL
    if any(k in msg for k in ["in use", "locked", "占用", "被占用", "无法访问"]):
        return ERROR_CATEGORY_FILE_IN_USE
    if any(k in msg for k in ["not found", "no such file", "不存在", "找不到"]):
        return ERROR_CATEGORY_NOT_FOUND
    if any(k in msg for k in ["ioerror", "oserror", "io", "读写"]):
        return ERROR_CATEGORY_IO
    return ERROR_CATEGORY_OTHER


class ProfileRunner(QThread):
    profile_started = pyqtSignal(str)
    profile_scan_progress = pyqtSignal(str, str)
    profile_sync_progress = pyqtSignal(str, int, int)
    profile_file_syncing = pyqtSignal(str, str)
    profile_finished = pyqtSignal(object)
    status_changed = pyqtSignal(str, str)

    def __init__(self, profile: SyncProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self._cancel = False
        self._tracker = SyncEventTracker.get_instance()
        self.result: Optional[ProfileResult] = None

    def cancel(self):
        self._cancel = True

    def _scan(self) -> List[DiffItem]:
        left_root = Path(self.profile.source_path)
        right_root = Path(self.profile.target_path)

        self.status_changed.emit(self.profile.profile_id, f"[{self.profile.name}] 正在扫描源目录 ...")
        left_files = scan_directory(
            left_root,
            progress_callback=lambda p: self.profile_scan_progress.emit(self.profile.profile_id, p),
            cancel_check=lambda: self._cancel
        )
        if self._cancel:
            return []

        self.status_changed.emit(self.profile.profile_id, f"[{self.profile.name}] 正在扫描目标目录 ...")
        right_files = scan_directory(
            right_root,
            progress_callback=lambda p: self.profile_scan_progress.emit(self.profile.profile_id, p),
            cancel_check=lambda: self._cancel
        )
        if self._cancel:
            return []

        self.status_changed.emit(self.profile.profile_id, f"[{self.profile.name}] 正在对比差异 ...")
        diffs = compare_files(left_files, right_files)
        return diffs

    def _build_tasks(self, diffs: List[DiffItem]) -> List[SyncTask]:
        tasks: List[SyncTask] = []
        idx = 0
        right_root = Path(self.profile.target_path)
        for diff in diffs:
            if self._cancel:
                break
            if diff.status in (
                DiffItem.STATUS_LEFT_ONLY,
                DiffItem.STATUS_DIFF_SIZE,
                DiffItem.STATUS_DIFF_TIME,
                DiffItem.STATUS_DIFF_BOTH
            ):
                if diff.left_file:
                    task = SyncTask(
                        index=idx,
                        rel_path=diff.rel_path,
                        source_path=diff.left_file.path,
                        target_path=right_root / diff.rel_path,
                        size=diff.left_file.size
                    )
                    tasks.append(task)
                    idx += 1
        return tasks

    def _copy_file(self, task: SyncTask, chunk_size: int = 1024 * 1024) -> None:
        source = task.source_path
        target = task.target_path

        self._tracker.mark_syncing(target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._tracker.mark_syncing(target.parent)

            total = task.size

            with open(source, "rb") as fsrc:
                with open(target, "wb") as fdst:
                    while True:
                        if self._cancel:
                            raise InterruptedError("用户取消同步")
                        chunk = fsrc.read(chunk_size)
                        if not chunk:
                            break
                        fdst.write(chunk)

            stat = source.stat()
            import os
            os.utime(target, (stat.st_atime, stat.st_mtime))

            self._tracker.unmark_syncing(target)
            self._tracker.unmark_syncing(target.parent)
        except Exception:
            self._tracker.unmark_syncing(target)
            self._tracker.unmark_syncing(target.parent)
            raise

    def run(self):
        self._cancel = False
        result = ProfileResult(
            profile_id=self.profile.profile_id,
            profile_name=self.profile.name,
            source_path=self.profile.source_path,
            target_path=self.profile.target_path,
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.result = result
        self.profile_started.emit(self.profile.profile_id)

        diffs = self._scan()
        if self._cancel:
            result.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.profile_finished.emit(result)
            return

        result.scan_total = len(diffs)
        for d in diffs:
            if d.status == DiffItem.STATUS_IDENTICAL:
                result.scan_identical += 1
            elif d.status == DiffItem.STATUS_LEFT_ONLY:
                result.scan_left_only += 1
            elif d.status == DiffItem.STATUS_RIGHT_ONLY:
                result.scan_right_only += 1
            else:
                result.scan_diff += 1

        tasks = self._build_tasks(diffs)
        result.total_files = len(tasks)
        if result.total_files == 0:
            result.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status_changed.emit(self.profile.profile_id, f"[{self.profile.name}] 没有需要同步的文件")
            self.profile_finished.emit(result)
            return

        synced_count = 0
        failed_count = 0
        skipped_count = 0

        self.profile_sync_progress.emit(self.profile.profile_id, 0, result.total_files)

        for i, task in enumerate(tasks):
            if self._cancel:
                break

            self.status_changed.emit(
                self.profile.profile_id,
                f"[{self.profile.name}] 同步中 ({i + 1}/{result.total_files}): {task.rel_path}"
            )
            self.profile_file_syncing.emit(self.profile.profile_id, task.rel_path)

            try:
                self._copy_file(task)
                synced_count += 1
            except InterruptedError:
                skipped_count += 1
                result.skipped_files.append(SkippedFile(
                    rel_path=task.rel_path,
                    reason="用户取消同步"
                ))
                break
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                result.failed_files.append(FailedFile(
                    rel_path=task.rel_path,
                    error_msg=error_msg,
                    error_category=categorize_error(error_msg)
                ))

            self.profile_sync_progress.emit(self.profile.profile_id, i + 1, result.total_files)

        result.success_count = synced_count
        result.failed_count = failed_count
        result.skipped_count = skipped_count
        result.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.status_changed.emit(
            self.profile.profile_id,
            f"[{self.profile.name}] 完成：成功 {synced_count} / 失败 {failed_count} / 跳过 {skipped_count}"
        )
        self.profile_finished.emit(result)


class TaskScheduler(QThread):
    MAX_CONCURRENT = 2

    scheduler_started = pyqtSignal(int)
    scheduler_progress = pyqtSignal(int, int)
    profile_queued = pyqtSignal(object)
    profile_running = pyqtSignal(object)
    profile_completed = pyqtSignal(object)
    all_completed = pyqtSignal(list)
    status_message = pyqtSignal(str)

    def __init__(self, profiles: List[SyncProfile], parent=None):
        super().__init__(parent)
        self.profiles = list(profiles)
        self._cancel = False
        self._queue: List[SyncProfile] = list(profiles)
        self._running: Dict[str, ProfileRunner] = {}
        self._completed: List[ProfileResult] = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._all_done_event = threading.Event()

    def cancel_all(self):
        self._cancel = True
        with self._lock:
            for runner in self._running.values():
                runner.cancel()
            self._condition.notify_all()

    def _start_next(self) -> bool:
        if self._cancel:
            return False
        if len(self._running) >= self.MAX_CONCURRENT:
            return False
        if not self._queue:
            return False

        profile = self._queue.pop(0)
        runner = ProfileRunner(profile)
        runner.profile_finished.connect(self._on_profile_finished)
        runner.status_changed.connect(self._on_runner_status)

        self._running[profile.profile_id] = runner
        self.profile_running.emit(profile)
        runner.start()
        return True

    def _on_runner_status(self, profile_id: str, msg: str):
        self.status_message.emit(msg)

    def _on_profile_finished(self, result: ProfileResult):
        with self._lock:
            if result.profile_id in self._running:
                del self._running[result.profile_id]
            self._completed.append(result)
            self._condition.notify_all()

        self.profile_completed.emit(result)
        total = len(self.profiles)
        done = len(self._completed)
        self.scheduler_progress.emit(done, total)

    def run(self):
        self._cancel = False
        self._queue = list(self.profiles)
        self._running = {}
        self._completed = []
        total = len(self.profiles)

        for p in self.profiles:
            self.profile_queued.emit(p)

        self.scheduler_started.emit(total)
        self.scheduler_progress.emit(0, total)
        self.status_message.emit(f"调度器启动：共 {total} 个方案，最大并发 {self.MAX_CONCURRENT} 个")

        while True:
            with self._lock:
                if self._cancel and not self._running:
                    break
                if not self._cancel and not self._queue and not self._running:
                    break
                while (not self._cancel and len(self._running) >= self.MAX_CONCURRENT) or \
                      (not self._cancel and not self._queue and self._running):
                    self._condition.wait(timeout=0.1)
                    break
                if self._cancel and not self._running:
                    break
                if not self._cancel and not self._queue and not self._running:
                    break

                started = self._start_next()
                if not started and not self._running:
                    break

        self.status_message.emit(f"调度器完成：已处理 {len(self._completed)} 个方案")
        self.all_completed.emit(self._completed)
