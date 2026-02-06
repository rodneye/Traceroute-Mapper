import csv
import ipaddress
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import requests


@dataclass
class GeoRecord:
    ip: str
    city: Optional[str]
    region: Optional[str]
    country: Optional[str]
    loc: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    org: Optional[str]


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_reserved or addr.is_loopback or addr.is_multicast)
    except ValueError:
        return False


def _parse_loc(loc: Optional[str]) -> (Optional[float], Optional[float]):
    if not loc:
        return None, None
    try:
        lat_str, lon_str = loc.split(",")
        return float(lat_str), float(lon_str)
    except Exception:
        return None, None


def _load_cache(cache_path: str) -> Dict[str, GeoRecord]:
    if not os.path.exists(cache_path):
        return {}
    cache: Dict[str, GeoRecord] = {}
    with open(cache_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ip = row.get("ip")
            if not ip:
                continue
            cache[ip] = GeoRecord(
                ip=ip,
                city=row.get("city") or None,
                region=row.get("region") or None,
                country=row.get("country") or None,
                loc=row.get("loc") or None,
                lat=float(row["lat"]) if row.get("lat") else None,
                lon=float(row["lon"]) if row.get("lon") else None,
                org=row.get("org") or None,
            )
    return cache


def _save_cache(cache_path: str, cache: Dict[str, GeoRecord]) -> None:
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", newline="") as f:
        fieldnames = ["ip", "city", "region", "country", "loc", "lat", "lon", "org"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in cache.values():
            writer.writerow(
                {
                    "ip": record.ip,
                    "city": record.city or "",
                    "region": record.region or "",
                    "country": record.country or "",
                    "loc": record.loc or "",
                    "lat": "" if record.lat is None else record.lat,
                    "lon": "" if record.lon is None else record.lon,
                    "org": record.org or "",
                }
            )


def geolocate_ips(
    ips: Iterable[str],
    cache_path: str,
    token: Optional[str],
    timeout: int = 5,
) -> Dict[str, GeoRecord]:
    cache = _load_cache(cache_path)

    session = requests.Session()

    for ip in sorted(set(ips)):
        if ip in cache:
            continue
        if not _is_public_ip(ip):
            cache[ip] = GeoRecord(
                ip=ip,
                city=None,
                region=None,
                country=None,
                loc=None,
                lat=None,
                lon=None,
                org=None,
            )
            continue

        url = f"https://ipinfo.io/{ip}/json"
        if token:
            url = f"{url}?token={token}"

        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            cache[ip] = GeoRecord(
                ip=ip,
                city=None,
                region=None,
                country=None,
                loc=None,
                lat=None,
                lon=None,
                org=None,
            )
            continue

        data = resp.json()
        loc = data.get("loc")
        lat, lon = _parse_loc(loc)
        cache[ip] = GeoRecord(
            ip=ip,
            city=data.get("city"),
            region=data.get("region"),
            country=data.get("country"),
            loc=loc,
            lat=lat,
            lon=lon,
            org=data.get("org"),
        )

    _save_cache(cache_path, cache)
    return cache
