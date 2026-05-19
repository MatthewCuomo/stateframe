"""Minimal command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

import stateframe as sf


def main() -> None:
    parser = argparse.ArgumentParser(prog="stateframe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="Profile a local data file.")
    profile_parser.add_argument("path", help="Path to a CSV, parquet, JSON, Excel, or zip file.")
    profile_parser.add_argument("--target", default=None)
    profile_parser.add_argument("--time", default=None)
    profile_parser.add_argument("--goal", default="first-look")
    profile_parser.add_argument("--mode", default="standard", choices=["quick", "standard", "deep"])

    args = parser.parse_args()
    if args.command == "profile":
        path = Path(args.path)
        result = sf.scan(
            path,
            target=args.target,
            time=args.time,
            goal=args.goal,
            scan_depth=args.mode,
        )
        print(result.to_markdown())


if __name__ == "__main__":
    main()
