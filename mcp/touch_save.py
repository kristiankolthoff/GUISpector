#!/usr/bin/env python3
"""
Refresh/save a file in-place to trigger file watchers.

Usage:
  python touch_save.py "C:\\full\\path\\to\\file.ext"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def refresh_file(path_str: str) -> None:
    file_path = Path(path_str)
    if not file_path.exists():
        raise FileNotFoundError(f"Path does not exist: {file_path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"Expected a file, got directory: {file_path}")

    # Read and write the same bytes to emit a write event on some watchers
    data: bytes
    with file_path.open("rb") as rf:
        data = rf.read()
    with file_path.open("r+b") as wf:
        wf.seek(0)
        wf.write(data)
        wf.truncate()
        try:
            wf.flush()
            os.fsync(wf.fileno())
        except Exception:
            # fsync may not be available/needed on some platforms
            pass

    # Ensure modification time is updated to now
    try:
        now = time.time()
        os.utime(file_path, (now, now))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-save a file to trigger watchers")
    parser.add_argument("file_path", help="Absolute path to the file to refresh")
    args = parser.parse_args(argv)
    try:
        refresh_file(args.file_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    else:
        print("refreshed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


