from typing import Dict, List

from geoip import GeoRecord
from traceroute_runner import Hop


def build_records(results: Dict[str, List[Hop]], geo: Dict[str, GeoRecord]) -> List[dict]:
    records = []
    for destination, hops in results.items():
        for hop in hops:
            record = {
                "destination": destination,
                "hop": hop.hop,
                "ip": hop.ip or "",
                "rtt_ms": hop.rtt_ms if hop.rtt_ms is not None else None,
                "reachable": hop.reachable,
                "city": "",
                "region": "",
                "country": "",
                "lat": None,
                "lon": None,
                "org": "",
            }
            if hop.ip and hop.ip in geo:
                g = geo[hop.ip]
                record.update(
                    {
                        "city": g.city or "",
                        "region": g.region or "",
                        "country": g.country or "",
                        "lat": g.lat if g.lat is not None else None,
                        "lon": g.lon if g.lon is not None else None,
                        "org": g.org or "",
                    }
                )
            records.append(record)
    return records
