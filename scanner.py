from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class FileInfo:
    path: Path
    size: int
    mtime: float


@dataclass
class DiffItem:
    rel_path: str
    status: str
    left_file: Optional[FileInfo] = None
    right_file: Optional[FileInfo] = None

    STATUS_LEFT_ONLY = "left_only"
    STATUS_RIGHT_ONLY = "right_only"
    STATUS_DIFF_SIZE = "diff_size"
    STATUS_DIFF_TIME = "diff_time"
    STATUS_DIFF_BOTH = "diff_both"
    STATUS_IDENTICAL = "identical"


def scan_directory(root: Path, progress_callback=None, cancel_check=None) -> Dict[str, FileInfo]:
    result: Dict[str, FileInfo] = {}
    root = root.resolve()

    if not root.exists() or not root.is_dir():
        return result

    try:
        for item in root.rglob("*"):
            if cancel_check and cancel_check():
                break

            try:
                if progress_callback:
                    progress_callback(str(item))

                if item.is_file():
                    rel_path = str(item.relative_to(root))
                    stat = item.stat()
                    result[rel_path] = FileInfo(
                        path=item,
                        size=stat.st_size,
                        mtime=stat.st_mtime
                    )
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass

    return result


def compare_files(
    left: Dict[str, FileInfo],
    right: Dict[str, FileInfo]
) -> list:
    diffs: list = []
    all_keys = set(left.keys()) | set(right.keys())

    for key in sorted(all_keys):
        lf = left.get(key)
        rf = right.get(key)

        if lf and not rf:
            diffs.append(DiffItem(
                rel_path=key,
                status=DiffItem.STATUS_LEFT_ONLY,
                left_file=lf
            ))
        elif rf and not lf:
            diffs.append(DiffItem(
                rel_path=key,
                status=DiffItem.STATUS_RIGHT_ONLY,
                right_file=rf
            ))
        else:
            size_diff = lf.size != rf.size
            time_diff = abs(lf.mtime - rf.mtime) > 1.0

            if size_diff and time_diff:
                diffs.append(DiffItem(
                    rel_path=key,
                    status=DiffItem.STATUS_DIFF_BOTH,
                    left_file=lf,
                    right_file=rf
                ))
            elif size_diff:
                diffs.append(DiffItem(
                    rel_path=key,
                    status=DiffItem.STATUS_DIFF_SIZE,
                    left_file=lf,
                    right_file=rf
                ))
            elif time_diff:
                diffs.append(DiffItem(
                    rel_path=key,
                    status=DiffItem.STATUS_DIFF_TIME,
                    left_file=lf,
                    right_file=rf
                ))
            else:
                diffs.append(DiffItem(
                    rel_path=key,
                    status=DiffItem.STATUS_IDENTICAL,
                    left_file=lf,
                    right_file=rf
                ))

    return diffs
