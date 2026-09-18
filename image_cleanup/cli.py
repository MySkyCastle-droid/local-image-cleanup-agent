"""Command line entry point for local image cleanup."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .delivery import export_delivery
from .models import model_dir, prepare_models
from .workspace import load_report, mark_box, mark_mask, process_batch, set_qa


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="image-cleanup")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare-models", help="Download and verify local model files")
    process = commands.add_parser("process", help="Process one image or a folder")
    process.add_argument("--source", type=Path, required=True)
    process.add_argument("--output", type=Path, required=True)
    process.add_argument("--authorized", action="store_true", required=True)
    process.add_argument("--detector", choices=("ocr", "none"), default="ocr")
    process.add_argument("--method", choices=("lama", "telea"), default="lama")
    process.add_argument("--gpu", action="store_true")
    process.add_argument("--only-id")
    process.add_argument("--max-new", type=int)
    process.add_argument("--force", action="store_true")
    mark = commands.add_parser("mark", help="Add or remove a local repair region")
    mark.add_argument("--output", type=Path, required=True)
    mark.add_argument("--id", required=True)
    region = mark.add_mutually_exclusive_group(required=True)
    region.add_argument("--box", help="x,y,width,height")
    region.add_argument("--mask-file", type=Path)
    mark.add_argument("--remove", action="store_true")
    qa = commands.add_parser("qa", help="Record a human QA decision")
    qa.add_argument("--output", type=Path, required=True)
    qa.add_argument("--id", required=True)
    qa.add_argument("--status", choices=("completed_manual", "needs_review", "imperfect"), required=True)
    qa.add_argument("--note", default="")
    export = commands.add_parser("export", help="Build client delivery ZIP")
    export.add_argument("--output", type=Path, required=True)
    report = commands.add_parser("status", help="Show aggregate local QA status")
    report.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review", help="Open local QA interface")
    review.add_argument("--source", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--port", type=int, default=8501)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare-models":
        prepare_models()
        print(f"Models ready in {model_dir()}")
    elif args.command == "process":
        source = args.source
        if source.is_file():
            source = source.parent
            from .workspace import item_id

            args.only_id = item_id(args.source.name)
        payload = process_batch(
            source, args.output, authorized=args.authorized, detector=args.detector,
            method=args.method, gpu=args.gpu, only_id=args.only_id,
            max_new=args.max_new, force=args.force,
        )
        print(json.dumps(payload["summary"], ensure_ascii=False))
        print(f"Local report: {args.output.resolve() / 'report.json'}")
        return 1 if payload["summary"]["failed"] else 0
    elif args.command == "mark":
        if args.box:
            box = [int(value.strip()) for value in args.box.split(",")]
            mark_box(args.output, args.id, box, remove=args.remove)
        else:
            if args.remove:
                raise ValueError("--remove is supported only with --box")
            mark_mask(args.output, args.id, args.mask_file)
        print("Mark saved. Rerun processing for this ID, then review the result.")
    elif args.command == "qa":
        set_qa(args.output, args.id, args.status, args.note)
        print("QA decision saved.")
    elif args.command == "export":
        print(export_delivery(args.output))
    elif args.command == "status":
        print(json.dumps(load_report(args.output).get("summary", {}), ensure_ascii=False))
    elif args.command == "review":
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        command = [
            sys.executable, "-m", "streamlit", "run",
            str(Path(__file__).with_name("review_ui.py")),
            "--server.address", "127.0.0.1", "--server.port", str(args.port),
            "--server.headless", "true", "--browser.gatherUsageStats", "false",
            "--client.toolbarMode", "minimal",
            "--", "--source", str(args.source.resolve()), "--output", str(args.output.resolve()),
        ]
        return subprocess.call(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
