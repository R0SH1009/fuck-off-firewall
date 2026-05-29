import re
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta

PORT_SCAN_THRESHOLD = 3
PORT_SCAN_WINDOW_SEC = 5
LARGE_TRANSFER_BYTES = 1_000_000  # 1 MB

sample_traffic = """2024-01-15 08:15:22 SRC:192.168.1.50 DST:8.8.8.8 PORT:53 PROTOCOL:DNS SIZE:256
2024-01-15 08:16:05 SRC:192.168.1.50 DST:142.251.41.14 PORT:443 PROTOCOL:HTTPS SIZE:1024
2024-01-15 08:17:33 SRC:192.168.1.100 DST:10.0.0.5 PORT:22 PROTOCOL:SSH SIZE:512
2024-01-15 08:18:01 SRC:203.0.113.45 DST:192.168.1.50 PORT:4444 PROTOCOL:UNKNOWN SIZE:2048
2024-01-15 08:18:02 SRC:203.0.113.45 DST:192.168.1.50 PORT:5555 PROTOCOL:UNKNOWN SIZE:2048
2024-01-15 08:18:03 SRC:203.0.113.45 DST:192.168.1.50 PORT:6666 PROTOCOL:UNKNOWN SIZE:2048
2024-01-15 08:19:15 SRC:192.168.1.75 DST:185.220.101.1 PORT:443 PROTOCOL:HTTPS SIZE:5242880
2024-01-15 09:22:44 SRC:192.168.1.80 DST:8.8.8.8 PORT:53 PROTOCOL:DNS SIZE:128"""

with open("network_traffic.txt", "w") as f:
    f.write(sample_traffic)

print("Network traffic file created!")


def parse_traffic_entry(line):
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) SRC:([\d.]+) DST:([\d.]+) PORT:(\d+) PROTOCOL:(\w+) SIZE:(\d+)'
    match = re.match(pattern, line)
    if match:
        return {
            "timestamp": match.group(1),
            "src_ip":    match.group(2),
            "dst_ip":    match.group(3),
            "port":      int(match.group(4)),
            "protocol":  match.group(5),
            "size":      int(match.group(6)),
        }
    return None


def detect_port_scans(df, threshold=PORT_SCAN_THRESHOLD, window_sec=PORT_SCAN_WINDOW_SEC):
    """Return dict of src_ip -> info for IPs hitting multiple ports in a short window."""
    window = timedelta(seconds=window_sec)
    suspicious = {}

    for src_ip, group in df.groupby("src_ip"):
        times = group["timestamp"].sort_values().tolist()
        ports = group.set_index("timestamp")["port"]

        for i in range(len(times)):
            in_window = [t for t in times[i:] if t - times[i] <= window]
            if len(in_window) >= threshold:
                ports_hit = group[
                    (group["timestamp"] >= times[i]) &
                    (group["timestamp"] <= times[i] + window)
                ]["port"].unique().tolist()

                if len(ports_hit) >= threshold:
                    suspicious[src_ip] = {
                        "src_ip":       src_ip,
                        "ports_hit":    ports_hit,
                        "hit_count":    len(ports_hit),
                        "window_start": times[i],
                        "window_end":   times[i] + window,
                    }
                    break

    return suspicious


def detect_large_transfers(df, threshold=LARGE_TRANSFER_BYTES):
    """Return rows where transfer size exceeds threshold."""
    large = df[df["size"] >= threshold].copy()
    results = []
    for _, row in large.iterrows():
        results.append({
            "timestamp": row["timestamp"],
            "src_ip":    row["src_ip"],
            "dst_ip":    row["dst_ip"],
            "port":      row["port"],
            "protocol":  row["protocol"],
            "size":      row["size"],
        })
    return results


def detect_unknown_protocols(df):
    """Return rows using UNKNOWN protocol."""
    unknown = df[df["protocol"] == "UNKNOWN"].copy()
    results = []
    for _, row in unknown.iterrows():
        results.append({
            "timestamp": row["timestamp"],
            "src_ip":    row["src_ip"],
            "dst_ip":    row["dst_ip"],
            "port":      row["port"],
            "size":      row["size"],
        })
    return results


def find_suspicious_patterns(parsed_traffic):
    """Flag unusual port usage and high-frequency talkers."""
    suspicious = []
    known_ports = {53, 80, 443, 22, 25, 21, 3389}
    src_counts = defaultdict(int)

    for entry in parsed_traffic:
        src_counts[entry["src_ip"]] += 1
        if entry["port"] not in known_ports and entry["protocol"] != "UNKNOWN":
            suspicious.append(
                f"Unusual port {entry['port']} used by {entry['src_ip']} "
                f"-> {entry['dst_ip']} ({entry['protocol']})"
            )

    top_talker_threshold = max(src_counts.values()) if src_counts else 0
    for ip, count in src_counts.items():
        if count == top_talker_threshold and count > 2:
            suspicious.append(f"Top talker: {ip} with {count} connections")

    return suspicious


def generate_alerts(port_scans, large_transfers, unknown_protos, patterns):
    alerts = []

    for ip, info in port_scans.items():
        alerts.append({
            "severity": "HIGH",
            "message":  (
                f"Port scan from {ip}: hit {info['hit_count']} ports "
                f"{info['ports_hit']} in {PORT_SCAN_WINDOW_SEC}s"
            ),
        })

    for entry in large_transfers:
        alerts.append({
            "severity": "MEDIUM",
            "message":  (
                f"Large transfer: {entry['src_ip']} -> {entry['dst_ip']} "
                f"{entry['size']:,} bytes on port {entry['port']}"
            ),
        })

    for entry in unknown_protos:
        alerts.append({
            "severity": "HIGH",
            "message":  (
                f"Unknown protocol: {entry['src_ip']} -> {entry['dst_ip']} "
                f"port {entry['port']}"
            ),
        })

    for pattern in patterns:
        alerts.append({"severity": "LOW", "message": pattern})

    return alerts


def generate_report(df, parsed_traffic, port_scans, large_transfers, alerts):
    report = []
    report.append("=" * 60)
    report.append("         NETWORK TRAFFIC ANALYSIS REPORT")
    report.append(f"Generated : {datetime.now()}")
    report.append("=" * 60)

    total_bytes = df["size"].sum()
    report.append(f"\nTotal entries   : {len(df)}")
    report.append(f"Total bytes     : {total_bytes:,}")
    report.append(f"Unique src IPs  : {df['src_ip'].nunique()}")
    report.append(f"Unique dst IPs  : {df['dst_ip'].nunique()}")
    report.append(f"Unique ports    : {df['port'].nunique()}")

    report.append("\n--- PROTOCOL BREAKDOWN ---")
    for proto, count in df["protocol"].value_counts().items():
        report.append(f"  {proto:<12} {count:>5} connections")

    report.append("\n--- TOP SOURCE IPs ---")
    for ip, count in df["src_ip"].value_counts().head(5).items():
        report.append(f"  {ip:<20} {count:>4} connections")

    report.append(f"\n--- THREATS DETECTED ---")
    if not alerts:
        report.append("  No threats detected.")
    for alert in alerts:
        report.append(f"  [{alert['severity']:6}] {alert['message']}")

    report.append("\n" + "=" * 60)
    report.append(f"  {len(port_scans)} port scan(s), "
                  f"{len(large_transfers)} large transfer(s) detected.")
    report.append("=" * 60)

    report_text = "\n".join(report)
    with open("network_traffic_report.txt", "w") as f:
        f.write(report_text)

    print(report_text)


# ── Load & parse ──────────────────────────────────────────────────────────────

traffic_entries = []
with open("network_traffic.txt", "r") as f:
    for line in f:
        line = line.strip()
        if line:
            traffic_entries.append(line)

parsed_traffic = [parse_traffic_entry(e) for e in traffic_entries]
parsed_traffic = [t for t in parsed_traffic if t]

print(f"Successfully parsed: {len(parsed_traffic)} traffic entries")
for entry in parsed_traffic[:3]:
    print(entry)

# ── Build DataFrame ───────────────────────────────────────────────────────────

df = pd.DataFrame(parsed_traffic)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

# ── Detect threats ────────────────────────────────────────────────────────────

port_scans      = detect_port_scans(df)
large_transfers = detect_large_transfers(df)
unknown_protos  = detect_unknown_protocols(df)
patterns        = find_suspicious_patterns(parsed_traffic)
alerts          = generate_alerts(port_scans, large_transfers, unknown_protos, patterns)

# ── Report ────────────────────────────────────────────────────────────────────

generate_report(df, parsed_traffic, port_scans, large_transfers, alerts)

print("\n✅ Analysis complete! Check network_traffic_report.txt for the full report.")
