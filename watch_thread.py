import os
import time
import threading
from pathlib import Path
from typing import Set, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
)


DEBOUNCE_INTERVAL_SEC = 3.0
SELF_EVENT_COOLDOWN_SEC = 8.0


class SyncEventTracker:
    _instance: Optional["SyncEventTracker"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._active_paths: Dict[str, float] = {}
        self._global_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SyncEventTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def mark_syncing(self, target_path: Path):
        with self._global_lock:
            try:
                key = str(Path(target_path).resolve())
            except (OSError, FileNotFoundError):
                key = str(Path(target_path).absolute())
            self._active_paths[key] = time.time()

    def unmark_syncing(self, target_path: Path):
        with self._global_lock:
            try:
                key = str(Path(target_path).resolve())
            except (OSError, FileNotFoundError):
                key = str(Path(target_path).absolute())
            if key in self._active_paths:
                self._active_paths[key] = time.time()

    def is_self_event(self, event_path: Path) -> bool:
        with self._global_lock:
            try:
                resolved = str(Path(event_path).resolve())
            except (OSError, FileNotFoundError):
                try:
                    resolved = str(Path(event_path).absolute())
                except Exception:
                    resolved = str(event_path)

            now = time.time()
            expired_keys = []
            found = False

            for key, mark_time in list(self._active_paths.items()):
                if now - mark_time > SELF_EVENT_COOLDOWN_SEC:
                    expired_keys.append(key)
                    continue
                if resolved == key or resolved.startswith(key + os.sep):
                    found = True

            for key in expired_keys:
                del self._active_paths[key]

            return found


class _WatchHandler(FileSystemEventHandler):
    def __init__(self, watcher: "WatchThread", watch_root: Path):
        super().__init__()
        self.watcher = watcher
        self.watch_root = watch_root.resolve()

    def _record_event(self, raw_path: str):
        try:
            p = Path(raw_path)
            try:
                resolved = p.resolve()
            except (OSError, FileNotFoundError):
                resolved = p.absolute()
            try:
                rel_path = resolved.relative_to(self.watch_root)
            except ValueError:
                return
            self.watcher._enqueue_change(str(rel_path))
        except Exception:
            pass

    def on_created(self, event):
        if not event.is_directory:
            self._record_event(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._record_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._record_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._record_event(event.dest_path)
            self._record_event(event.src_path)


class WatchThread(QThread):
    changes_detected = pyqtSignal(list)
    status_changed = pyqtSignal(str)
    watch_started = pyqtSignal()
    watch_stopped = pyqtSignal()

    def __init__(self, source_path: str, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self._stop_event = threading.Event()
        self._observer: Optional[Observer] = None
        self._changed_paths: Set[str] = set()
        self._changed_lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_lock = threading.Lock()
        self._tracker = SyncEventTracker.get_instance()
        self._handler: Optional[_WatchHandler] = None

    def _enqueue_change(self, rel_path: str):
        full_path = self.source_path / rel_path
        if self._tracker.is_self_event(full_path):
            return

        with self._changed_lock:
            self._changed_paths.add(rel_path)

        with self._debounce_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                DEBOUNCE_INTERVAL_SEC, self._flush_changes
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _flush_changes(self):
        with self._debounce_lock:
            self._debounce_timer = None

        with self._changed_lock:
            if not self._changed_paths:
                return
            changed = sorted(self._changed_paths)
            self._changed_paths.clear()

        self.status_changed.emit(
            f"检测到 {len(changed)} 个文件变化，防抖收集完成，准备同步 ..."
        )
        self.changes_detected.emit(changed)

    def run(self):
        self._stop_event.clear()
        self._observer = Observer()
        self._handler = _WatchHandler(self, self.source_path)
        self._observer.schedule(self._handler, str(self.source_path), recursive=True)

        try:
            self._observer.start()
        except OSError as e:
            self.status_changed.emit(f"启动监控失败: {e}")
            return

        self.status_changed.emit(f"开始监控源目录: {self.source_path}")
        self.watch_started.emit()

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(0.5)
        finally:
            with self._debounce_lock:
                if self._debounce_timer is not None:
                    self._debounce_timer.cancel()
                    self._debounce_timer = None

            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
            self._handler = None
            self.watch_stopped.emit()
            self.status_changed.emit("监控已停止")

    def stop(self):
        self._stop_event.set()
