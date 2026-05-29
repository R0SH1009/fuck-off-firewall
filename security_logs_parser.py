import re
import pandas as pd
from datetime import datetime, timedelta

BRUTE_FORCE_THRESHOLD = 3
BRUTE_FORCE_WINDOW_MIN = 5

sample_logs = """2024-01-15 08:23:11 user:john_doe IP:192.168.1.10 STATUS:FAILED
2024-01-15 08:23:45 user:john_doe IP:192.168.1.10 STATUS:FAILED
2024-01-15 08:24:02 user:john_doe IP:192.168.1.10 STATUS:FAILED
2024-01-15 09:15:33 user:jane_smith IP:10.0.0.5 STATUS:SUCCESS
2024-01-15 11:42:17 user:admin IP:203.0.113.99 STATUS:FAILED
2024-01-15 11:42:18 user:admin IP:203.0.113.99 STATUS:FAILED
2024-01-15 11:42:55 user:admin IP:203.0.113.99 STATUS:FAILED
2024-01-15 23:58:01 user:bob_jones IP:192.168.1.55 STATUS:SUCCESS"""

with open("security_logs.txt", "w") as f:
    f.write(sample_logs)

print("Log file created!")


def parse_log_entry(line):
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) user:(\w+) IP:([\d.]+) STATUS:(\w+)'
    match = re.match(pattern, line)
    if match:
        return {
            "timestamp": match.group(1),
            "username":  match.group(2),
            "ip":        match.group(3),
            "status":    match.group(4)
        }
    return None


def detect_brute_force(df, threshold=BRUTE_FORCE_THRESHOLD, window_minutes=BRUTE_FORCE_WINDOW_MIN):
    window = timedelta(minutes=window_minutes)
    suspicious = {}

    failed_df = df[df["status"] == "FAILED"].sort_values("timestamp")

    for ip, group in failed_df.groupby("ip"):
        times = group["timestamp"].tolist()
        for i in range(len(times)):
            count = sum(1 for t in times[i:] if t - times[i] <= window)
            if count >= threshold:
                suspicious[ip] = {
                    "ip":             ip,
                    "failed_count":   len(times),
                    "window_start":   times[i],
                    "window_end":     times[i] + window,
                    "users_targeted": group["username"].unique().tolist(),
                }
                break

    return suspicious


log_entries = []

with open("security_logs.txt", "r") as f:
    for line in f:
        line = line.strip()
        if line:
            log_entries.append(line)
            print(line)

print(f"\nTotal entries loaded: {len(log_entries)}")

parsed_logs = [parse_log_entry(entry) for entry in log_entries]
parsed_logs = [log for log in parsed_logs if log]

print(f"Successfully parsed: {len(parsed_logs)} entries")

df = pd.DataFrame(parsed_logs, columns=["timestamp", "username", "ip", "status"])
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

total         = len(df)
failed_count  = len(df[df["status"] == "FAILED"])
success_count = len(df[df["status"] == "SUCCESS"])
unique_ips    = df["ip"].nunique()
unique_users  = df["username"].nunique()

ip_failure_counts = (
    df[df["status"] == "FAILED"]
    .groupby("ip")
    .size()
    .sort_values(ascending=False)
    .rename("failed_attempts")
)

suspicious = detect_brute_force(df)

print("\n" + "=" * 60)
print("           SECURITY LOG ANALYSIS REPORT")
print("=" * 60)
print(f"Log file  : security_logs.txt")
print(f"Analyzed  : {total} entries  |  "
      f"Date range: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")

print("\n--- SUMMARY STATISTICS ---")
print(f"Total login attempts : {total}")
print(f"  Successful         : {success_count}  ({success_count/total*100:.1f}%)")
print(f"  Failed             : {failed_count}  ({failed_count/total*100:.1f}%)")
print(f"Unique IPs seen      : {unique_ips}")
print(f"Unique users seen    : {unique_users}")

print("\n--- FAILED ATTEMPTS BY IP ---")
if ip_failure_counts.empty:
    print("  No failed attempts recorded.")
else:
    print(f"  {'IP':<20} {'Failed Attempts':>15}")
    print(f"  {'-'*20} {'-'*15}")
    for ip, count in ip_failure_counts.items():
        print(f"  {ip:<20} {count:>15}")

print(f"\n--- THREAT DETECTION (Brute Force: {BRUTE_FORCE_THRESHOLD}+ failures in {BRUTE_FORCE_WINDOW_MIN} min) ---")
if not suspicious:
    print("  No brute force activity detected.")
else:
    for ip, info in suspicious.items():
        print(f"\n[!] SUSPICIOUS IP: {ip}")
        print(f"    Failed attempts   : {info['failed_count']}")
        print(f"    Window            : {info['window_start']}  ->  {info['window_end']}")
        print(f"    Users targeted    : {info['users_targeted']}")

print("\n" + "=" * 60)
print(f"  {len(suspicious)} suspicious IP(s) detected. Recommend firewall review.")
print("=" * 60)
