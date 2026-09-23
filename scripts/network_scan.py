import subprocess
import re

command = ["nmap", "-sn", "192.168.0.0/24"]

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print(result.stderr.strip())
else:
    current_device = None
    devices = []

    for line in result.stdout.splitlines():
        report_match = re.match(
            r"Nmap scan report for (?:(.*?) \(([\d.]+)\)|([\d.]+))",
            line
        )
        if report_match:
            if current_device:
                devices.append(current_device)
            current_device = {
                "name": report_match.group(1) or "unbekannt",
                "ip": report_match.group(2) or report_match.group(3),
                "manufacturer": "unbekannt"
            }
            continue

        if current_device:
            mac_match = re.search(r"MAC Address: [0-9A-F:]+ \((.*?)\)", line)
            if mac_match:
                current_device["manufacturer"] = mac_match.group(1)

    if current_device:
        devices.append(current_device)

    print(f"Gefundene Geräte: {len(devices)}")
    for device in devices:
        print(
            f"IP: {device['ip']} | "
            f"Hersteller: {device['manufacturer']}"
        )