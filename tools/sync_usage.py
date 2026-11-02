#!/usr/bin/env python3
"""Export subscription quotas to iCloud; never export credentials or conversations."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import json
import math
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time


DEFAULT_OUTPUT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/AI Usage/usage.json"


class QuotaError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise QuotaError("残量データの形式が変わりました。")
    return value


def normalize_codex(result, measured_at):
    limits = result.get("rateLimitsByLimitId") or {}
    quota = limits.get("codex") or result.get("rateLimits")
    if not isinstance(quota, dict):
        raise QuotaError("Codexの残量を取得できませんでした。")
    windows = []
    for key in ("primary", "secondary"):
        raw = quota.get(key)
        if raw is None:
            continue
        duration = number(raw["windowDurationMins"])
        used = number(raw["usedPercent"])
        reset = number(raw["resetsAt"])
        if not 0 <= used <= 100:
            raise QuotaError("Codexの残量が範囲外です。")
        window_id, label = {300: ("session", "5時間"), 10080: ("weekly", "週間")}.get(
            duration, ("window_" + str(int(duration)), str(int(duration)) + "分"))
        windows.append({"id": window_id, "label": label, "remainingPercent": 100 - used,
                        "resetsAt": datetime.fromtimestamp(reset, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                        "resetLabel": None})
    balance = (quota.get("credits") or {}).get("balance")
    if balance is not None:
        try:
            parsed = Decimal(str(balance))
            if not parsed.is_finite() or parsed < 0:
                raise InvalidOperation
            balance = str(parsed)
        except (InvalidOperation, ValueError):
            raise QuotaError("クレジット残高を読み込めませんでした。") from None
    return {"id": "codex", "name": "Codex", "status": "connected", "measuredAt": measured_at,
            "windows": windows, "credits": balance, "message": None}


def fetch_codex():
    executable = shutil.which("codex")
    if not executable:
        candidate = Path.home() / ".local/bin/codex"
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise QuotaError("Codex CLIが見つかりません。")
    process = subprocess.Popen([executable, "app-server", "--stdio", "-c", "mcp_servers={}"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, bufsize=0)
    def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()
    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "ai-usage-widget", "version": "1.0.0"}, "capabilities": {}}})
        deadline = time.monotonic() + 30
        pending = b""
        while time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], min(1, max(0, deadline - time.monotonic())))[0]:
                continue
            chunk = os.read(process.stdout.fileno(), 65_536)
            if not chunk:
                raise QuotaError("Codex CLIとの接続が終了しました。")
            pending += chunk
            if len(pending) > 1_048_576:
                raise QuotaError("Codex CLIの応答を読み込めませんでした。")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if "error" in message and message.get("id") in (1, 2):
                    raise QuotaError("Codexでログインを確認してから同期してください。")
                if message.get("id") == 1:
                    send({"method": "initialized"})
                    send({"id": 2, "method": "account/rateLimits/read", "params": {}})
                elif message.get("id") == 2:
                    return normalize_codex(message["result"], utc_now())
        raise QuotaError("Codexの残量取得が時間切れになりました。")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def parse_claude_usage(text, measured_at):
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).replace("\r", "\n")
    headings = list(re.finditer(r"Current (?:session|week[^\n]*)", text, re.IGNORECASE))
    windows = {}
    for index, match in enumerate(headings):
        title = match.group().strip()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[match.end():end]
        percentage = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(used|left|remaining)", section, re.IGNORECASE)
        if not percentage:
            continue
        value = float(percentage.group(1))
        if not 0 <= value <= 100:
            raise QuotaError("Claudeの残量が範囲外です。")
        remaining = 100 - value if percentage.group(2).lower() == "used" else value
        if "session" in title.lower():
            key, label = "session", "5時間"
        elif "all models" in title.lower() or title.lower() == "current week":
            key, label = "weekly", "週間"
        else:
            key = "model_weekly"
            model = re.search(r"\(([^)]+)\)", title)
            label = ((model.group(1).replace(" only", "") + " 週") if model else "モデル週")[:48]
        reset = re.search(r"Resets\s+([^\n]+)", section, re.IGNORECASE)
        windows[key] = {"id": key, "label": label, "remainingPercent": remaining,
                        "resetsAt": None, "resetLabel": (reset.group(1).strip()[:96] if reset else None)}
    if not windows:
        raise QuotaError("Claude Codeで /usage を開き、初回設定とログインを確認してください。")
    return {"id": "claude", "name": "Claude", "status": "connected", "measuredAt": measured_at,
            "windows": list(windows.values()), "credits": None, "message": None}


def fetch_claude():
    executable = shutil.which("claude")
    if not executable:
        return disconnected_claude()
    auth = subprocess.run([executable, "auth", "status", "--json"], capture_output=True, text=True, timeout=15)
    try:
        authenticated = json.loads(auth.stdout).get("loggedIn") is True
    except ValueError:
        raise QuotaError("Claude Codeのログイン状態を確認できませんでした。") from None
    if not authenticated:
        return disconnected_claude()
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 160, 0, 0))
    process = None
    try:
        # /usage is a built-in CLI command, not a model prompt. Safe mode disables user hooks.
        process = subprocess.Popen([executable, "/usage", "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
                                    "--mcp-config", '{"mcpServers":{}}', "--tools", ""],
                                   cwd=str(Path.home()), stdin=slave, stdout=slave, stderr=slave,
                                   start_new_session=True)
        os.close(slave)
        slave = None
        raw = b""
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if not select.select([master], [], [], 1)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65_536)
            except OSError:
                break
            if not chunk:
                break
            raw += chunk
            if len(raw) > 1_048_576:
                raise QuotaError("Claude Codeの画面を読み込めませんでした。")
            try:
                result = parse_claude_usage(raw.decode("utf-8", errors="replace"), utc_now())
                if {"session", "weekly"} <= {w["id"] for w in result["windows"]}:
                    return result
            except QuotaError:
                pass
        return parse_claude_usage(raw.decode("utf-8", errors="replace"), utc_now())
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        os.close(master)
        if slave is not None:
            os.close(slave)


def disconnected_claude():
    return {"id": "claude", "name": "Claude", "status": "disconnected", "measuredAt": None,
            "windows": [], "credits": None, "message": "MacでClaude Codeにログインしてください。"}


def retain_after_failure(provider_id, message, previous):
    old = next((p for p in previous.get("providers", []) if p.get("id") == provider_id), None)
    if old and old.get("measuredAt"):
        return {**old, "status": "stale", "message": message}
    return {"id": provider_id, "name": "Codex" if provider_id == "codex" else "Claude",
            "status": "error", "measuredAt": None, "windows": [], "credits": None, "message": message}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.expanduser()
    if args.output == DEFAULT_OUTPUT and not (Path.home() / "Library/Mobile Documents/com~apple~CloudDocs").is_dir():
        print("iCloud Driveを有効にしてから実行してください。", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    # Serialize this tool's runs without putting a lock file in iCloud.
    lock_dir = Path.home() / "Library/Caches/com.ryo.AIUsageBoard"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "sync.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("同期はすでに実行中です。")
            return 0
        try:
            previous = json.loads(output.read_text()) if output.exists() else {}
        except (OSError, ValueError):
            previous = {}
        providers = []
        failed = False
        for provider_id, fetch in [("codex", fetch_codex), ("claude", fetch_claude)]:
            try:
                provider = fetch()
            except Exception as error:
                failed = True
                message = str(error) if isinstance(error, QuotaError) else "残量を取得できませんでした。"
                provider = retain_after_failure(provider_id, message, previous)
            providers.append(provider)
        snapshot = {"schemaVersion": 1, "generatedAt": utc_now(), "providers": providers}
        temporary = output.with_name("." + output.name + ".tmp")
        try:
            with temporary.open("w") as stream:
                json.dump(snapshot, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        for provider in providers:
            summary = ", ".join(w["label"] + ": " + f'{w["remainingPercent"]:g}%' for w in provider["windows"])
            print(provider["name"] + " / " + provider["status"] + (" / " + summary if summary else ""))
        print("保存先: " + str(output))
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
