"""python -m quarry [--days N] – process recent SEC filings and write public/feed.json."""
import argparse
import os
from datetime import date
from pathlib import Path

from quarry.pipeline import run
from quarry.sec_client import SecClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarry SEC pipeline")
    parser.add_argument("--days", type=int, default=7, help="how many past days to process if missing")
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="public/feed.json")
    args = parser.parse_args()

    user_agent = os.environ.get("QUARRY_USER_AGENT", "Quarry tim.mehrbrey@gmail.com")
    run(SecClient(user_agent), today=date.today(), data_dir=Path(args.data), feed_path=Path(args.out), process_days=args.days)


if __name__ == "__main__":
    main()
