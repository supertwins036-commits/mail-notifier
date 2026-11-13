"""お名前.com のメールボックスを IMAP で確かめ、指定した差出人からの新着を Discord に知らせる。

GitHub Actions から定期的に動かす想定。設定はすべて環境変数(GitHub Secrets)で渡す。

    IMAP_HOST            IMAP サーバー名(例: mail1234.onamae.ne.jp)
    IMAP_PORT            省略時 993(SSL)
    IMAP_USER            メールアドレス(ログイン名)
    IMAP_PASSWORD        メールのパスワード
    IMAP_FOLDER          省略時 INBOX
    WATCH_FROM           見張る差出人。複数はカンマ区切り。「a@x.jp」はアドレス全体、
                         「*@x.jp」はそのドメインのすべて、「yamada*@*」は yamada で始まる人
                         (「*」は @ 以外の0文字以上。大文字小文字は区別しない)
    DISCORD_WEBHOOK_URL  通知先の Discord Webhook URL

既に知らせたメールは state.json(最後に見た UID)で覚える。
初回は「いまある分」を既読扱いにして、過去のメールをまとめて通知しない。
メールの本文は読まない・ログに出さない(公開リポジトリでもログから漏れないように)。
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

STATE_PATH = Path(__file__).with_name("state.json")
DISCORD_TIMEOUT_SEC = 20
IMAP_TIMEOUT_SEC = 30
# 一度に知らせる上限。設定の誤りで大量に飛ばないように。超えた分は次の回に回る。
MAX_NOTIFY_PER_RUN = 10


class ConfigError(Exception):
    pass


@dataclass
class Config:
    host: str
    port: int
    user: str
    password: str
    folder: str
    watch_from: frozenset[str]
    webhook_url: str


@dataclass
class MailInfo:
    uid: int
    from_addr: str
    from_display: str
    subject: str
    date: str


def load_config(env: dict[str, str]) -> Config:
    missing = [k for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD", "WATCH_FROM", "DISCORD_WEBHOOK_URL")
               if not env.get(k, "").strip()]
    if missing:
        raise ConfigError(f"環境変数が設定されていません: {', '.join(missing)}")
    try:
        port = int(env.get("IMAP_PORT", "").strip() or "993")
    except ValueError as e:
        raise ConfigError("IMAP_PORT は数字で指定してください") from e
    watch = parse_watch_list(env["WATCH_FROM"])
    if not watch:
        raise ConfigError("WATCH_FROM に有効なメールアドレスがありません")
    webhook = env["DISCORD_WEBHOOK_URL"].strip()
    if not webhook.startswith("https://"):
        raise ConfigError("DISCORD_WEBHOOK_URL は https:// で始まる必要があります")
    return Config(
        host=env["IMAP_HOST"].strip(),
        port=port,
        user=env["IMAP_USER"].strip(),
        password=env["IMAP_PASSWORD"],
        folder=env.get("IMAP_FOLDER", "").strip() or "INBOX",
        watch_from=watch,
        webhook_url=webhook,
    )


def parse_watch_list(raw: str) -> frozenset[str]:
    """見張る差出人の指定を読む。「*」は「@ 以外の0文字以上」を表す。

    boss@example.com   その人だけ
    *@example.com      そのドメインのすべて(サブドメインは含まない)
    yamada*@*        yamada で始まる人(ドメインは問わない)

    すべてに一致する「*@*」や、形のおかしいものは無視する(大量の通知を防ぐ)。
    """
    result = set()
    for item in raw.split(","):
        item = item.strip().lower()
        if item.startswith("@"):
            item = "*" + item
        if item.count("@") != 1:
            continue
        local, _, domain = item.partition("@")
        if not local or not domain:
            continue
        if local.strip("*") == "" and domain.strip("*") == "":
            print(f"警告: すべてのメールに一致する指定 {item} は無視します", file=sys.stderr)
            continue
        if "*" not in domain and "." not in domain:
            continue
        result.add(item)
    return frozenset(result)


def _pattern_to_regex(pattern: str) -> re.Pattern:
    body = "[^@]*".join(re.escape(p) for p in pattern.split("*"))
    return re.compile(f"^{body}$")


def is_watched(addr: str, watch: frozenset[str]) -> bool:
    """大文字小文字は区別しない。"""
    addr = addr.strip().lower()
    if addr.count("@") != 1:
        return False
    return any(_pattern_to_regex(p).match(addr) for p in watch)


def decode_header_value(raw: str | None) -> str:
    """=?ISO-2022-JP?B?...?= のような符号化された見出しを読める文字列に戻す。"""
    if not raw:
        return ""
    parts = []
    for text, charset in email.header.decode_header(raw):
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "ascii", errors="replace"))
            except LookupError:  # 知らない文字コード名
                parts.append(text.decode("utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts).replace("\r", "").replace("\n", "").strip()


def parse_headers(uid: int, header_bytes: bytes) -> MailInfo:
    msg = email.message_from_bytes(header_bytes)
    display, addr = email.utils.parseaddr(decode_header_value(msg.get("From")))
    return MailInfo(
        uid=uid,
        from_addr=addr.strip().lower(),
        from_display=display,
        subject=decode_header_value(msg.get("Subject")) or "(件名なし)",
        date=msg.get("Date", ""),
    )


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("last_uid"), int) or not isinstance(data.get("uidvalidity"), int):
        raise ValueError(f"{path.name} の形式が正しくありません")
    return data


def save_state(path: Path, uidvalidity: int, last_uid: int) -> None:
    path.write_text(json.dumps({"uidvalidity": uidvalidity, "last_uid": last_uid}, indent=2) + "\n",
                    encoding="utf-8")


def build_discord_payload(mail: MailInfo) -> dict:
    who = f"{mail.from_display} <{mail.from_addr}>" if mail.from_display else mail.from_addr
    return {
        "username": "メール通知",
        "content": f"📧 **{mail.from_addr}** からメールが届きました",
        "embeds": [{
            "title": mail.subject[:250],
            "fields": [
                {"name": "差出人", "value": who[:1000], "inline": False},
                {"name": "日時", "value": (mail.date or "不明")[:100], "inline": False},
            ],
        }],
        "allowed_mentions": {"parse": []},  # 件名に @everyone があっても鳴らさない
    }


def send_discord(webhook_url: str, payload: dict) -> None:
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "mail-notifier/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DISCORD_TIMEOUT_SEC) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Discord への送信に失敗しました(HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        # URL を含めないで報告する
        raise RuntimeError(f"Discord への送信に失敗しました(HTTP {e.code})") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Discord に接続できませんでした: {e.reason}") from None


class Mailbox:
    """imaplib を薄く包む。テストでは同じ形の偽物に差し替える。"""

    def __init__(self, cfg: Config):
        self._imap = imaplib.IMAP4_SSL(cfg.host, cfg.port, timeout=IMAP_TIMEOUT_SEC)
        self._imap.login(cfg.user, cfg.password)
        typ, data = self._imap.select(f'"{cfg.folder}"', readonly=True)  # 既読にしない
        if typ != "OK":
            raise RuntimeError(f"フォルダ {cfg.folder} を開けませんでした")
        typ, data = self._imap.response("UIDVALIDITY")
        if not data or data[0] is None:
            raise RuntimeError("UIDVALIDITY を取得できませんでした")
        self.uidvalidity = int(data[0])

    def max_uid(self) -> int:
        typ, data = self._imap.uid("SEARCH", None, "ALL")
        uids = data[0].split() if typ == "OK" and data and data[0] else []
        return max((int(u) for u in uids), default=0)

    def uids_after(self, last_uid: int) -> list[int]:
        typ, data = self._imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
        if typ != "OK":
            raise RuntimeError("メールの検索に失敗しました")
        uids = [int(u) for u in (data[0].split() if data and data[0] else [])]
        # 「n:*」は新着が無くても最後の1通を返すことがあるので除く
        return sorted(u for u in uids if u > last_uid)

    def fetch_headers(self, uid: int) -> bytes:
        typ, data = self._imap.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK":
            raise RuntimeError(f"UID {uid} の見出しを取得できませんでした")
        for item in data:
            if isinstance(item, tuple) and len(item) == 2:
                return item[1]
        raise RuntimeError(f"UID {uid} の見出しが空でした")

    def close(self) -> None:
        try:
            self._imap.logout()
        except Exception:
            pass


def run(cfg: Config, box, state_path: Path, notify=send_discord) -> int:
    """新着を調べて知らせる。知らせた件数を返す。"""
    state = load_state(state_path)

    if state is None or state["uidvalidity"] != box.uidvalidity:
        # 初回、またはサーバー側で UID が振り直された: いまある分は知らせずに基準だけ決める
        reason = "初回の実行のため" if state is None else "UIDVALIDITY が変わったため"
        baseline = box.max_uid()
        save_state(state_path, box.uidvalidity, baseline)
        print(f"{reason}、いまあるメールは通知せず基準を UID {baseline} にしました")
        return 0

    last_uid = state["last_uid"]
    new_uids = box.uids_after(last_uid)
    print(f"新しいメール {len(new_uids)} 通を確認します")
    sent = 0
    for uid in new_uids:
        info = parse_headers(uid, box.fetch_headers(uid))
        if is_watched(info.from_addr, cfg.watch_from):
            if sent >= MAX_NOTIFY_PER_RUN:
                print(f"通知が上限 {MAX_NOTIFY_PER_RUN} 件に達したので、残りは次の回にします")
                break
            notify(cfg.webhook_url, build_discord_payload(info))
            sent += 1
        # 1通ごとに進める: 途中で失敗しても、知らせた分を二度知らせない
        last_uid = uid
        save_state(state_path, box.uidvalidity, last_uid)
    print(f"{sent} 件を Discord に知らせました")
    return sent


def main() -> int:
    try:
        cfg = load_config(dict(os.environ))
    except ConfigError as e:
        print(f"設定の誤り: {e}", file=sys.stderr)
        return 2
    box = None
    try:
        box = Mailbox(cfg)
        run(cfg, box, STATE_PATH)
        return 0
    except imaplib.IMAP4.error as e:
        print(f"IMAP のエラー(ログイン名・パスワード・サーバー名を確かめてください): {e}", file=sys.stderr)
        return 1
    except Exception as e:  # 失敗したら Actions を赤にして GitHub からメールで気づけるようにする
        print(f"失敗しました: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        if box is not None:
            box.close()


if __name__ == "__main__":
    sys.exit(main())
