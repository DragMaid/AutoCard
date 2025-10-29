"""Utility helpers used by Makefile for cross-platform operations.

Usage:
  python scripts/make_utils.py rmpath <path>        # remove file or dir at path
  python scripts/make_utils.py clean --venv <venv>  # remove __pycache__, ml runs/saves and venv
"""
import argparse
import shutil
import sys
from pathlib import Path


def rmpath(path: Path) -> int:
    if not path.exists():
        print(f"Path does not exist: {path}")
        return 0
    try:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"Removed directory: {path}")
        else:
            path.unlink()
            print(f"Removed file: {path}")
        return 0
    except Exception as e:
        print(f"Error removing {path}: {e}", file=sys.stderr)
        return 2


def remove_pycache(root: Path) -> int:
    count = 0
    for p in root.rglob('__pycache__'):
        try:
            shutil.rmtree(p)
            print(f"Removed: {p}")
            count += 1
        except Exception as e:
            print(f"Error removing {p}: {e}", file=sys.stderr)
    print(f"Removed {count} __pycache__ directories")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')

    p_rmpath = sub.add_parser('rmpath')
    p_rmpath.add_argument('path', type=Path)

    p_clean = sub.add_parser('clean')
    p_clean.add_argument('--root', type=Path, default=Path('.'))

    args = parser.parse_args(argv)

    if args.cmd == 'rmpath':
        return rmpath(args.path)
    if args.cmd == 'clean':
        remove_pycache(args.root)
        return 0

    parser.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
