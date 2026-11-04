#!/usr/bin/env python3
"""Export subscription quotas to iCloud; never export credentials or conversations."""

import argparse
import codecs
from datetime import datetime, timezone, timedelta
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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TerminalScreen:
    def __init__(self, rows=48, columns=160):
        self.rows, self.columns = rows, columns
        self.cells = [[' '] * columns for _ in range(rows)]
        self.row = self.column = 0
        self.saved = (0, 0)
        self.pending = ''

    def feed(self, text):
        self.pending += text
        i = 0
        while i < len(self.pending):
            char = self.pending[i]
            if char == '\x1b':
                if i + 1 >= len(self.pending):
                    break
                kind = self.pending[i + 1]
                if kind == '[':
                    match = re.match(r'\x1b\[([0-?]*)([ -/]*)([@-~])', self.pending[i:])
                    if not match:
                        break
                    params, _, command = match.groups()
                    if not params.startswith(('?', '>', '<', '=')):
                        try:
                            values = [int(v or 0) for v in params.split(';')]
                        except ValueError:
                            values = [0]
                        n = values[0] or 1
                        if command in ('H', 'f'):
                            self.row = n - 1
                            self.column = (values[1] or 1) - 1 if len(values) > 1 else 0
                        elif command == 'A': self.row -= n
                        elif command == 'B': self.row += n
                        elif command == 'C': self.column += n
                        elif command == 'D': self.column -= n
                        elif command == 'G': self.column = n - 1
                        elif command == 'J':
                            mode = values[0]
                            if mode in (2, 3):
                                self.cells = [[' '] * self.columns for _ in range(self.rows)]
                            elif mode == 0:
                                self.cells[self.row][self.column:] = [' '] * (self.columns - self.column)
                                for row in range(self.row + 1, self.rows):
                                    self.cells[row] = [' '] * self.columns
                            elif mode == 1:
                                for row in range(self.row):
                                    self.cells[row] = [' '] * self.columns
                                self.cells[self.row][:self.column + 1] = [' '] * (self.column + 1)
                        elif command == 'K':
                            start = 0 if values[0] in (1, 2) else self.column
                            end = self.columns if values[0] != 1 else self.column + 1
                            self.cells[self.row][start:end] = [' '] * (end - start)
                    self.row = min(max(self.row, 0), self.rows - 1)
                    self.column = min(max(self.column, 0), self.columns - 1)
                    i += len(match.group())
                    continue
                if kind == ']':
                    end = re.search(r'\x07|\x1b\\', self.pending[i + 2:])
                    if not end:
                        break
                    i += 2 + end.end()
                    continue
                if kind == '7': self.saved = (self.row, self.column)
                elif kind == '8': self.row, self.column = self.saved
                # ESC ( B selects a character set; consume the final byte too.
                if kind == '(':
                    if i + 2 >= len(self.pending): break
                    i += 3
                else: i += 2
                continue
            if char == '\r': self.column = 0
            elif char == '\n': self.row = min(self.row + 1, self.rows - 1)
            elif char == '\b': self.column = max(0, self.column - 1)
            elif char >= ' ':
                self.cells[self.row][self.column] = char
                self.column = min(self.column + 1, self.columns - 1)
            i += 1
        self.pending = self.pending[i:]
        if len(self.pending) > 4096:
            self.pending = ''

    def text(self):
        return '\n'.join(''.join(row).rstrip() for row in self.cells)


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


def claude_reset_time(label, measured_at):
    # Only convert the explicit CLI clock/date and named timezone; keep unknown formats as text.
    match = re.fullmatch(r"(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}) at )?(\d{1,2})(?::(\d{2}))?(am|pm) \(([^)]+)\)", label, re.IGNORECASE)
    if not match:
        return None
    month, day, hour, minute, meridian, zone = match.groups()
    try:
        local = datetime.fromisoformat(measured_at.replace("Z", "+00:00")).astimezone(ZoneInfo(zone))
        hour = int(hour)
        if not 1 <= hour <= 12:
            return None
        target = local.replace(hour=hour % 12 + (12 if meridian.lower() == "pm" else 0),
                               minute=int(minute or 0), second=0, microsecond=0)
        if month:
            months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
            target = target.replace(month=months.index(month.lower()) + 1, day=int(day))
            if local.month == 12 and target.month == 1:
                next_year = target.replace(year=target.year + 1)
                if timedelta(0) < next_year - local <= timedelta(days=7):
                    target = next_year
        elif target <= local:
            next_day = target + timedelta(days=1)
            # A session is five hours. Do not move an already expired clock a full day forward.
            if timedelta(0) < next_day - local <= timedelta(hours=5):
                target = next_day
        return target.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, ZoneInfoNotFoundError):
        return None


def parse_claude_usage(text, measured_at):
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[(\d*)C", lambda m: " " * min(int(m.group(1) or 1), 160), text)
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
        reset_label = reset.group(1).strip()[:96] if reset else None
        windows[key] = {"id": key, "label": label, "remainingPercent": remaining,
                        "resetsAt": claude_reset_time(reset_label, measured_at) if reset_label else None, "resetLabel": reset_label}
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
    workspace = Path.home() / "Library/Caches/com.ryo.AIUsageBoard/claude-workspace"
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 160, 0, 0))
    process = None
    try:
        # /usage is a built-in CLI command, not a model prompt. Safe mode disables user hooks.
        process = subprocess.Popen([executable, "--safe-mode", "--setting-sources", "", "--strict-mcp-config",
                                    "--mcp-config", '{"mcpServers":{}}', "--tools", ""],
                                   cwd=str(workspace), stdin=slave, stdout=slave, stderr=slave,
                                   start_new_session=True)
        os.close(slave)
        slave = None
        terminal = TerminalScreen()
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        received = 0
        candidate = None
        trusted = False
        requested = False
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if not select.select([master], [], [], 1)[0]:
                if candidate is not None and "refreshing" not in terminal.text().lower():
                    return candidate
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65_536)
            except OSError:
                break
            if not chunk:
                break
            received += len(chunk)
            if received > 1_048_576:
                raise QuotaError("Claude Codeの画面を読み込めませんでした。")
            terminal.feed(decoder.decode(chunk))
            screen = terminal.text()
            candidate = None
            if not trusted and "Yes,Itrustthisfolder" in re.sub(r"\s+", "", screen):
                # The dedicated empty workspace contains no project hooks or instructions.
                os.write(master, b"\x1b[B")
                time.sleep(0.2)
                os.write(master, b"\r")
                trusted = True
                continue
            if not requested and "❯" in screen and "trustthisfolder" not in re.sub(r"\s+", "", screen):
                os.write(master, b"/usage")
                time.sleep(0.2)
                os.write(master, b"\r")
                requested = True
                continue
            try:
                result = parse_claude_usage(screen, utc_now())
                if {"session", "weekly"} <= {w["id"] for w in result["windows"]}:
                    candidate = result
            except QuotaError:
                pass
        raise QuotaError("Claudeの残量画面を確認できませんでした。更新待ちです。")
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


def preserve_unavailable(provider, previous):
    """Keep the original sample time when a formerly available quota disappears."""
    old = next((p for p in previous.get("providers", []) if p.get("id") == provider["id"]), None)
    if not old or not old.get("measuredAt"):
        return provider
    missing = {w["id"] for w in old.get("windows", [])} - {w["id"] for w in provider.get("windows", [])}
    missing_credits = old.get("credits") is not None and provider.get("credits") is None
    if provider["status"] != "connected" or missing or missing_credits:
        return retain_after_failure(provider["id"], provider.get("message") or "一部の枠を取得できませんでした。更新待ちです。", previous)
    return provider


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
                provider = preserve_unavailable(fetch(), previous)
                failed = failed or provider["status"] == "stale"
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
