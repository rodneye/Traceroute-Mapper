import ipaddress
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
RTT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ms")


@dataclass
class Hop:
    hop: int
    ip: Optional[str]
    rtt_ms: Optional[float]
    reachable: bool


def _validate_ip(value: str) -> None:
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address: {value}") from exc


def _find_traceroute_binary() -> str:
    path = shutil.which("traceroute")
    if not path:
        raise FileNotFoundError(
            "traceroute binary not found. Install it (e.g., 'sudo apt-get install traceroute')."
        )
    return path


def run_traceroute(
    destination: str,
    source: Optional[str] = None,
    max_hops: int = 30,
    timeout: int = 2,
    queries: int = 1,
) -> List[Hop]:
    _validate_ip(destination)
    if source:
        _validate_ip(source)

    traceroute_bin = _find_traceroute_binary()

    cmd = [
        traceroute_bin,
        "-n",
        "-q",
        str(queries),
        "-w",
        str(timeout),
        "-m",
        str(max_hops),
    ]
    if source:
        cmd += ["-s", source]
    cmd.append(destination)

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(
            f"Traceroute failed (exit {proc.returncode}). stderr: {proc.stderr.strip()}"
        )

    hops: List[Hop] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip header like: traceroute to 8.8.8.8 (8.8.8.8), 30 hops max
        if line.lower().startswith("traceroute"):
            continue

        parts = line.split()
        try:
            hop_num = int(parts[0])
        except (ValueError, IndexError):
            continue

        ip_match = IP_RE.search(line)
        rtt_match = RTT_RE.search(line)

        ip = ip_match.group(1) if ip_match else None
        rtt = float(rtt_match.group(1)) if rtt_match else None
        reachable = ip is not None

        hops.append(Hop(hop=hop_num, ip=ip, rtt_ms=rtt, reachable=reachable))

    return hops


def trace_targets(
    targets: List[str],
    source: Optional[str],
    max_hops: int,
    timeout: int,
    queries: int,
) -> dict:
    results = {}
    for target in targets:
        hops = run_traceroute(
            destination=target,
            source=source,
            max_hops=max_hops,
            timeout=timeout,
            queries=queries,
        )
        results[target] = hops
    return results
