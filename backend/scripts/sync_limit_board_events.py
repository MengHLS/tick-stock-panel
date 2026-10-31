"""Backfill the derived limit-board table from local minutes or Fuyao pools."""

from __future__ import annotations

import argparse
import json
from datetime import date, time, timedelta
from pathlib import Path

from app.config import settings
from app.custom.limit_board_events.minute_adapter import list_minute_partitions
from app.custom.limit_board_events.service import (
    ensure_limit_board_config,
    sync_limit_board_events,
)
from app.market_time import cn_now, cn_today
from app.plugins.fuyao.client import FuyaoError

_MINUTE_COMPLETE_AFTER = time(15, 30)


def _default_minute_end() -> date:
    current = cn_now()
    if current.time() >= _MINUTE_COMPLETE_AFTER:
        return current.date()
    return current.date() - timedelta(days=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    parser.add_argument("--source", choices=("minute", "fuyao"), default="minute")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    args = parser.parse_args()

    if args.source == "minute":
        start = args.start or date(2019, 1, 1)
        default_end = _default_minute_end()
        end = min(args.end or default_end, default_end)
    else:
        start = args.start or cn_today()
        end = args.end or start
    if end < start:
        parser.error("Choose an ordered date range")
    if args.source == "fuyao" and (end - start).days >= 120:
        parser.error("Fuyao history is limited to 120 calendar days per run")

    # The shared credential store resolves its path from process settings.
    settings.data_dir = args.data_dir
    try:
        ensure_limit_board_config(args.data_dir)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 1

    if args.source == "minute":
        days = list(reversed(list_minute_partitions(args.data_dir, start, end)))
    else:
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    for day in days:
        try:
            result = sync_limit_board_events(
                args.data_dir,
                day,
                create_config=False,
                source=args.source,
            )
        except (FuyaoError, ValueError, OSError) as exc:
            print(
                json.dumps(
                    {
                        "date": day.isoformat(),
                        "status": "error",
                        "message": str(exc),
                    }
                )
            )
            return 1
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
