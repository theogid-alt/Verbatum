from __future__ import annotations

import argparse
import json

from verbatim.analytics.latency import summarize_call_events
from verbatim.config import get_settings
from verbatim.events import load_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Verbatim v2 latency events.")
    parser.add_argument("--call-id")
    args = parser.parse_args()
    settings = get_settings()
    summary = summarize_call_events(load_events(settings.instrumentation.event_log_path), call_id=args.call_id)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
