"""Read a UTF-8 file or stdin; output JSON without storing conversations."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from .engine import analyze


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="chat2work", description="วิเคราะห์บทสนทนาธุรกิจไทยพร้อมหลักฐาน (Thai conversation-to-action analysis)")
    parser.add_argument("file", nargs="?", help="UTF-8 conversation file; omit or '-' for stdin")
    parser.add_argument("--reference-date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="date the conversation took place; enables resolution of unambiguous relative dates")
    parser.add_argument("--customer", action="append", default=[], metavar="NAME", help="extra speaker label to treat as the customer")
    parser.add_argument("--business", action="append", default=[], metavar="NAME", help="extra speaker label to treat as the business")
    parser.add_argument("--compact", action="store_true", help="single-line JSON")
    args = parser.parse_args(argv)
    if args.file and args.file != "-":
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = sys.stdin.buffer.read().decode("utf-8")
    try:
        analysis = analyze(text, reference_date=args.reference_date,
                           customer_speakers=set(args.customer), business_speakers=set(args.business))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=None if args.compact else 2))
