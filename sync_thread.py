import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Set

from PyQt5.QtCore import QThread, pyqtSignal

from scanner import DiffItem, FileInfo
from watch_thread import SyncEventTracker


@dataclass
class SyncTask:
    index: int
    rel_path: str
    source_path: Path
    target_path: Path
    size: int
    status: str = "pending"
    error_msg: str = ""

    STATUS_PENDING = "pending"
    STATUS_COPYING = "copying"
    STATUS_SYNCED = "synced"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"


class SyncThread(QThread):
    task_list_ready = pyqtSignal(list)
    file_started = pyqtSignal(int)
    file_progress = pyqtSignal(int, int)
    file_finished = pyqtSignal(int, str, str)
    overall_progress = pyqtSignal(int, int)
    sync_complete = pyqtSignal(int, int, int)
    status_changed = pyqtSignal(str)

    def __init__(
        self,
        left_path: str,
        right_path: str,
        diffs: List[DiffItem],
        only_paths: Optional[List[str]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.left_path = Path(left_path)
        self.right_path = Path(right_path)
        self.diffs = diffs
        self.only_paths: Optional[Set[str]] = set(only_paths) if only_paths else None
        self._cancel = False
        self.tasks: List[SyncTask] = []
        self._tracker = SyncEventTracker.get_instance()

    def cancel(self):
        self._cancel = True

    def _is_cancelled(self) -> bool:
        return self._cancel

    def _build_task_list(self) -> List[SyncTask]:
        tasks: List[SyncTask] = []
        idx = 0
        for diff in self.diffs:
            if self._cancel:
                break

            if self.only_paths is not None and diff.rel_path not in self.only_paths:
                continue

            if diff.status in (
                DiffItem.STATUS_LEFT_ONLY,
                DiffItem.STATUS_DIFF_SIZE,
                DiffItem.STATUS_DIFF_TIME,
                DiffItem.STATUS_DIFF_BOTH
            ):
                if diff.left_file:
                    source = diff.left_file.path
                    target = self.right_path / diff.rel_path
                    task = SyncTask(
                        index=idx,
                        rel_path=diff.rel_path,
                        source_path=source,
                        target_path=target,
                        size=diff.left_file.size
                    )
                    tasks.append(task)
                    idx += 1
        return tasks

    def _copy_file_with_progress(
        self,
        task: SyncTask,
        chunk_size: int = 1024 * 1024
    ) -> None:
        source = task.source_path
        target = task.target_path

        self._tracker.mark_syncing(target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._tracker.mark_syncing(target.parent)

            total = task.size
            copied = 0

            with open(source, "rb") as fsrc:
                with open(target, "wb") as fdst:
                    while True:
                        if self._cancel:
                            raise InterruptedError("用户取消同步")

                        chunk = fsrc.read(chunk_size)
                        if not chunk:
                            break
                        fdst.write(chunk)
                        copied += len(chunk)
                        self.file_progress.emit(task.index, copied)

            stat = source.stat()
            os.utime(target, (stat.st_atime, stat.st_mtime))

            self._tracker.unmark_syncing(target)
            self._tracker.unmark_syncing(target.parent)
        except Exception:
            self._tracker.unmark_syncing(target)
            self._tracker.unmark_syncing(target.parent)
            raise

    def run(self):
        self._cancel = False

        self.status_changed.emit("正在生成任务清单 ...")
        self.tasks = self._build_task_list()
        self.task_list_ready.emit(self.tasks)

        total_files = len(self.tasks)
        if total_files == 0:
            self.status_changed.emit("没有需要同步的文件")
            self.sync_complete.emit(0, 0, 0)
            return

        synced_count = 0
        failed_count = 0
        skipped_count = 0

        self.overall_progress.emit(0, total_files)

        for i, task in enumerate(self.tasks):
            if self._cancel:
                self.status_changed.emit("同步已取消")
                break

            self.status_changed.emit(f"正在同步 ({i + 1}/{total_files}): {task.rel_path}")
            self.file_started.emit(task.index)

            try:
                self._copy_file_with_progress(task)
                task.status = SyncTask.STATUS_SYNCED
                synced_count += 1
                self.file_finished.emit(task.index, SyncTask.STATUS_SYNCED, "")
            except InterruptedError:
                task.status = SyncTask.STATUS_SKIPPED
                skipped_count += 1
                self.file_finished.emit(task.index, SyncTask.STATUS_SKIPPED, "已取消")
                break
            except Exception as e:
                task.status = SyncTask.STATUS_FAILED
                task.error_msg = str(e)
                failed_count += 1
                self.file_finished.emit(task.index, SyncTask.STATUS_FAILED, str(e))

            self.overall_progress.emit(i + 1, total_files)

        if not self._cancel:
            self.status_changed.emit(
                f"同步完成：成功 {synced_count} 个，失败 {failed_count} 个"
            )
        self.sync_complete.emit(synced_count, failed_count, skipped_count)
