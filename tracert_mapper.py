import argparse
import csv
import os
from datetime import datetime
from typing import List

from geoip import geolocate_ips
from records import build_records
from traceroute_runner import trace_targets


def _parse_targets(value: str) -> List[str]:
    targets = [t.strip() for t in value.split(",") if t.strip()]
    if not targets:
        raise argparse.ArgumentTypeError("No valid targets provided")
    return targets


def _write_csv(path: str, records: List[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fieldnames = [
        "destination",
        "hop",
        "ip",
        "rtt_ms",
        "reachable",
        "city",
        "region",
        "country",
        "lat",
        "lon",
        "org",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Traceroute multiple targets and geolocate hops via IPinfo",
    )
    parser.add_argument(
        "--targets",
        required=True,
        type=_parse_targets,
        help="Comma-separated list of destination IPs",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Source IP address to bind (may require root privileges)",
    )
    parser.add_argument("--max-hops", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=2)
    parser.add_argument("--queries", type=int, default=1)
    parser.add_argument(
        "--geo-cache",
        default="data/geocache.csv",
        help="Path to IP geolocation cache CSV",
    )
    parser.add_argument(
        "--out-csv",
        default=None,
        help="Output CSV path (default: traceroute_YYYYMMDD_HHMMSS.csv)",
    )
    parser.add_argument(
        "--ipinfo-token",
        default=os.environ.get("IPINFO_TOKEN"),
        help="IPinfo token (default: IPINFO_TOKEN env var)",
    )

    args = parser.parse_args()

    if not args.out_csv:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        args.out_csv = f"traceroute_{timestamp}.csv"

    print(f"Tracing {len(args.targets)} target(s)...")
    results = trace_targets(
        targets=args.targets,
        source=args.source,
        max_hops=args.max_hops,
        timeout=args.timeout,
        queries=args.queries,
    )

    hop_ips = [hop.ip for hops in results.values() for hop in hops if hop.ip]

    print(f"Geolocating {len(set(hop_ips))} hop IP(s)...")
    geo = geolocate_ips(hop_ips, cache_path=args.geo_cache, token=args.ipinfo_token)

    records = build_records(results, geo)

    _write_csv(args.out_csv, records)
    print(f"Wrote CSV: {args.out_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
