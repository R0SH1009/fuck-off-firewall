import re
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

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


def find_suspicious_patterns(parsed_logs):
    suspicious = []
    ip_users = defaultdict(set)
    hour_activity = defaultdict(list)

    for log in parsed_logs:
        ip_users[log["ip"]].add(log["username"])
        hour = datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S").hour
        hour_activity[hour].append(log)

    # Multiple users from same IP
    for ip, users in ip_users.items():
        if len(users) > 1:
            suspicious.append(
                f"⚠️ Multiple users from IP {ip}: {users}"
            )

    # After hours logins (before 6am or after 10pm)
    for hour, logs in hour_activity.items():
        if hour < 6 or hour > 22:
            for log in logs:
                suspicious.append(
                    f"🌙 After-hours login: {log['username']} at {log['timestamp']}"
                )

    return suspicious


def generate_alerts(failed_logins, patterns):
    alerts = []

    for user, count in failed_logins.items():
        if count >= 3:
            alerts.append({
                "severity": "HIGH",
                "message": f"Brute force detected: {user} failed {count} times"
            })
        elif count == 2:
            alerts.append({
                "severity": "MEDIUM",
                "message": f"Multiple failures: {user} failed {count} times"
            })

    for pattern in patterns:
        alerts.append({
            "severity": "HIGH",
            "message": pattern
        })

    return alerts


def generate_report(parsed_logs, failed_logins, alerts):
    report = []
    report.append("=" * 50)
    report.append("SECURITY LOG ANALYSIS REPORT")
    report.append(f"Generated: {datetime.now()}")
    report.append("=" * 50)
    report.append(f"\nTotal Log Entries: {len(parsed_logs)}")
    report.append(f"Total Alerts: {len(alerts)}")
    report.append(f"\nFailed Login Summary:")

    for user, count in failed_logins.items():
        report.append(f"  - {user}: {count} failures")

    report.append("\nActive Alerts:")
    for alert in alerts:
        report.append(f"  [{alert['severity']}] {alert['message']}")

    report.append("=" * 50)

    report_text = "\n".join(report)

    with open("security_report.txt", "w") as f:
        f.write(report_text)

    print(report_text)


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

failed_logins = {}
for log in parsed_logs:
    if log["status"] == "FAILED":
        user = log["username"]
        failed_logins[user] = failed_logins.get(user, 0) + 1

print("\n--- Failed Login Counts ---")
for user, count in failed_logins.items():
    flag = " ⚠️ SUSPICIOUS" if count >= 3 else ""
    print(f"{user}: {count} failures{flag}")

ip_tracker = {}
for log in parsed_logs:
    ip = log["ip"]
    ip_tracker[ip] = ip_tracker.get(ip, 0) + 1

print("\n--- IP Address Activity ---")
for ip, count in ip_tracker.items():
    flag = " 🚨 INVESTIGATE" if count == 1 else ""
    print(f"{ip}: {count} attempts{flag}")

patterns = find_suspicious_patterns(parsed_logs)
print("\n--- Suspicious Patterns ---")
for p in patterns:
    print(p)

alerts = generate_alerts(failed_logins, patterns)
print("\n--- ALERTS ---")
for alert in alerts:
    print(f"[{alert['severity']}] {alert['message']}")

generate_report(parsed_logs, failed_logins, alerts)

# Add more complex test scenarios
extra_logs = """2024-01-15 03:15:00 user:hacker IP:203.0.113.99 STATUS:FAILED
2024-01-15 03:15:01 user:hacker IP:203.0.113.99 STATUS:FAILED
2024-01-15 03:15:02 user:hacker IP:203.0.113.99 STATUS:FAILED
2024-01-15 03:15:03 user:hacker IP:203.0.113.99 STATUS:FAILED
2024-01-15 03:15:04 user:hacker IP:203.0.113.99 STATUS:SUCCESS"""

with open("security_logs.txt", "a") as f:
    f.write("\n" + extra_logs)

# Re-run everything with new data
log_entries = []
with open("security_logs.txt", "r") as f:
    for line in f:
        line = line.strip()
        if line:
            log_entries.append(line)

parsed_logs = [parse_log_entry(entry) for entry in log_entries]
parsed_logs = [log for log in parsed_logs if log]
failed_logins = {}
for log in parsed_logs:
    if log["status"] == "FAILED":
        user = log["username"]
        failed_logins[user] = failed_logins.get(user, 0) + 1

patterns = find_suspicious_patterns(parsed_logs)
alerts = generate_alerts(failed_logins, patterns)
generate_report(parsed_logs, failed_logins, alerts)

print("\n✅ Project Complete! Check security_report.txt for your full report.")
