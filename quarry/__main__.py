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
    parser.add_argument("--no-profiles", action="store_true", help="skip index.json and company profiles")
    parser.add_argument("--profile-limit", type=int, help="write at most N profiles (for testing)")
    args = parser.parse_args()

    user_agent = os.environ.get("QUARRY_USER_AGENT", "Quarry tim.mehrbrey@gmail.com")
    run(SecClient(user_agent), today=date.today(), data_dir=Path(args.data), feed_path=Path(args.out), process_days=args.days,
        profiles=not args.no_profiles, profile_limit=args.profile_limit)


if __name__ == "__main__":
    main()
