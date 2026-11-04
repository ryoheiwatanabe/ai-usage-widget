#!/usr/bin/env python3
"""Build a native folder-authorized collector and prepare its 15-minute LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL = "com.ryo.AIUsageBoard.collector-check"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.name != "usage-m1-check.json":
        parser.error("確認用usage-m1-check.jsonを指定してください。共有usage.jsonは変更しません。")
    codex = shutil.which("codex")
    if not codex or not shutil.which("swiftc"):
        parser.error("ログイン済みCodex CLIとSwiftコンパイラが必要です。")
    home = Path.home()
    job = home / "Library/LaunchAgents" / (LABEL + ".plist")
    domain = "gui/" + str(os.getuid())
    loaded = subprocess.run(["/bin/launchctl", "print", domain + "/" + LABEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if (job.exists() or loaded):
        parser.error("確認用ジョブは既に存在します。既存設定は変更しません。")
    directories = [str(Path(codex).parent)]
    claude = shutil.which("claude")
    if claude:
        directories.append(str(Path(claude).parent))
    directories += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    runtime = home / "Library/Application Support/AIUsage"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    (runtime / "collector").mkdir(exist_ok=True, mode=0o700)
    app = home / "Applications/AI Usage Collector.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    executable = contents / "MacOS/AIUsageCollector"
    source = Path(__file__).with_name("CollectorBridge.swift")
    subprocess.run(["/usr/bin/swiftc", "-parse-as-library", "-O", str(source), str(source.parent.parent / "Shared/UsageSnapshot.swift"), "-o", str(executable)], check=True)
    info = {"CFBundleIdentifier": "com.ryo.AIUsageBoard.collector", "CFBundleName": "AI Usage Collector",
            "CFBundleExecutable": "AIUsageCollector", "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
            "CollectorSuggestedFolder": str(output.parent), "CollectorPython": sys.executable, "CollectorPath": ":".join(dict.fromkeys(directories))}
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
    shutil.copyfile(Path(__file__).with_name("sync_usage.py"), runtime / "sync_usage.py")
    logs = home / "Library/Logs/AIUsage"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    job.parent.mkdir(parents=True, exist_ok=True)
    config = {"Label": LABEL, "ProgramArguments": [str(executable), "--sync"],
              "StartInterval": 900, "RunAtLoad": True, "ProcessType": "Background",
              "StandardOutPath": str(logs / "collector.log"), "StandardErrorPath": str(logs / "collector-error.log")}
    job.write_bytes(plistlib.dumps(config)); job.chmod(0o600)
    subprocess.run(["/usr/bin/open", str(app), "--args", "--setup"], check=True)
    print("開いた画面で、iCloud DriveのAI Usageフォルダを選んでください。")
    print("ローカル表示用: " + str(runtime / "collector/usage-m1-check.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
