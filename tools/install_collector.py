#!/usr/bin/env python3
"""Install a 15-minute macOS collector. An explicit output path is required."""
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
        parser.error("切り替え前は確認用ファイル名を指定してください。共有usage.jsonへの切り替えは旧Mac停止後に行います。")
    codex = shutil.which("codex")
    if not codex:
        parser.error("ログイン済みのCodex CLIが必要です。")
    # Apple's command-line stub can receive a different TCC decision than Python.app.
    # Launch the app interpreter directly so the user can grant that exact app access.
    app_python = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    interpreter = str(app_python) if app_python.is_file() else sys.executable
    home = Path.home()
    job = home / "Library/LaunchAgents" / (LABEL + ".plist")
    domain = "gui/" + str(os.getuid())
    loaded = subprocess.run(["/bin/launchctl", "print", domain + "/" + LABEL],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if job.exists() or loaded:
        parser.error("確認用ジョブは既に存在します。既存設定は変更しません。")
    directories = [str(Path(codex).parent)]
    claude = shutil.which("claude")
    if claude:
        directories.append(str(Path(claude).parent))
    directories += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    runtime = home / "Library/Application Support/AIUsage"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    installed_script = runtime / "sync_usage.py"
    shutil.copyfile(Path(__file__).with_name("sync_usage.py"), installed_script)
    installed_script.chmod(0o600)
    logs = home / "Library/Logs/AIUsage"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    job.parent.mkdir(parents=True, exist_ok=True)
    config = {"Label": LABEL, "ProgramArguments": [interpreter, str(installed_script),
              "--output", str(output)], "EnvironmentVariables": {"PATH": ":".join(dict.fromkeys(directories))},
              "StartInterval": 900, "RunAtLoad": True, "ProcessType": "Background",
              "StandardOutPath": str(logs / "collector.log"), "StandardErrorPath": str(logs / "collector-error.log")}
    with job.open("xb") as stream:
        plistlib.dump(config, stream)
    job.chmod(0o600)
    try:
        subprocess.run(["/bin/launchctl", "bootstrap", domain, str(job)], check=True)
    except subprocess.CalledProcessError:
        print("登録に失敗しました。設定ファイルを残しました: " + str(job), file=sys.stderr)
        return 1
    print("15分ごとの確認用取得を登録しました: " + str(output))
    print("停止: launchctl bootout " + domain + "/" + LABEL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
