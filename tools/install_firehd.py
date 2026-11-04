#!/usr/bin/env python3
"""Install the read-only Fire HD dashboard for one device on trusted Wi-Fi."""
import argparse
import ipaddress
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL = "com.ryo.AIUsageBoard.firehd"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--address", required=True, type=ipaddress.IPv4Address)
    parser.add_argument("--device-ip", required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    for ip in (args.address, args.device_ip):
        if not ip.is_private or ip.is_loopback or ip.is_unspecified:
            parser.error("同じWi-Fi上のLANアドレスを指定してください。")
    home = Path.home()
    domain = "gui/" + str(os.getuid())
    job = home / "Library/LaunchAgents" / (LABEL + ".plist")
    loaded = subprocess.run(["/bin/launchctl", "print", domain + "/" + LABEL],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if job.exists() or loaded:
        parser.error("既存のFire HD設定は変更しません。")
    runtime = home / "Library/Application Support/AIUsage"
    (runtime / "tools").mkdir(parents=True, exist_ok=True, mode=0o700)
    (runtime / "firehd").mkdir(parents=True, exist_ok=True, mode=0o700)
    repo = Path(__file__).resolve().parent.parent
    for relative in ("tools/serve_firehd.py", "firehd/index.html"):
        shutil.copyfile(repo / relative, runtime / relative)
    logs = home / "Library/Logs/AIUsage"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    job.parent.mkdir(parents=True, exist_ok=True)
    config = {"Label": LABEL, "ProgramArguments": ["/usr/bin/caffeinate", "-i", sys.executable, str(runtime / "tools/serve_firehd.py"),
              "--source", str(args.source.expanduser().resolve()), "--bind", str(args.address), "--allow", str(args.device_ip)],
              "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 30, "ProcessType": "Background",
              "StandardOutPath": str(logs / "firehd.log"), "StandardErrorPath": str(logs / "firehd-error.log")}
    with job.open("xb") as stream:
        plistlib.dump(config, stream)
    job.chmod(0o600)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(job)], check=True)
    print("Fire HDで開くURL: http://" + str(args.address) + ":8765")
    return 0


if __name__ == "__main__":
    sys.exit(main())
