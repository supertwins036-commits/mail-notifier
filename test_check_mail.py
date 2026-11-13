import json
import tempfile
import unittest
from pathlib import Path

import check_mail as cm

ENV_OK = {
    "IMAP_HOST": "mail.example.jp",
    "IMAP_USER": "me@example.jp",
    "IMAP_PASSWORD": "dummy",
    "WATCH_FROM": "Boss@Example.com, other@example.com",
    "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/x/y",
}


def header(from_, subject="件名"):
    subj = cm.email.header.Header(subject, "utf-8").encode()
    return f"From: {from_}\r\nSubject: {subj}\r\nDate: Fri, 13 Nov 2026 10:00:00 +0900\r\n\r\n".encode()


class FakeBox:
    def __init__(self, mails: dict[int, bytes], uidvalidity=1):
        self.mails = mails
        self.uidvalidity = uidvalidity

    def max_uid(self):
        return max(self.mails, default=0)

    def uids_after(self, last_uid):
        return sorted(u for u in self.mails if u > last_uid)

    def fetch_headers(self, uid):
        return self.mails[uid]


class ConfigTest(unittest.TestCase):
    def test_ok_and_watch_list_lowercased(self):
        cfg = cm.load_config(ENV_OK)
        self.assertEqual(cfg.watch_from, {"boss@example.com", "other@example.com"})
        self.assertEqual(cfg.port, 993)
        self.assertEqual(cfg.folder, "INBOX")

    def test_missing_values(self):
        env = dict(ENV_OK, IMAP_PASSWORD="", WATCH_FROM=" ")
        with self.assertRaises(cm.ConfigError) as ctx:
            cm.load_config(env)
        self.assertIn("IMAP_PASSWORD", str(ctx.exception))
        self.assertIn("WATCH_FROM", str(ctx.exception))

    def test_bad_port_and_webhook(self):
        with self.assertRaises(cm.ConfigError):
            cm.load_config(dict(ENV_OK, IMAP_PORT="abc"))
        with self.assertRaises(cm.ConfigError):
            cm.load_config(dict(ENV_OK, DISCORD_WEBHOOK_URL="http://insecure"))


class WatchTest(unittest.TestCase):
    def test_domain_wildcard(self):
        watch = cm.parse_watch_list("*@KS-SYS.jp, @other.jp, boss@example.com")
        self.assertEqual(watch, {"*@ks-sys.jp", "*@other.jp", "boss@example.com"})
        self.assertTrue(cm.is_watched("Taro@ks-sys.JP", watch))
        self.assertTrue(cm.is_watched("a@other.jp", watch))
        self.assertTrue(cm.is_watched("boss@example.com", watch))
        self.assertFalse(cm.is_watched("x@sub.ks-sys.jp", watch))   # サブドメインは別
        self.assertFalse(cm.is_watched("x@ks-sys.jp.evil.com", watch))
        self.assertFalse(cm.is_watched("x@example.com", watch))
        self.assertFalse(cm.is_watched("", watch))

    def test_invalid_entries_ignored(self):
        self.assertEqual(cm.parse_watch_list("*@*, @, abc, *@nodot"), frozenset())


class HeaderTest(unittest.TestCase):
    def test_japanese_subject_and_display_name(self):
        name = cm.email.header.Header("上司", "iso-2022-jp").encode()
        info = cm.parse_headers(5, header(f"{name} <Boss@Example.com>", "会議の件"))
        self.assertEqual(info.from_addr, "boss@example.com")
        self.assertEqual(info.from_display, "上司")
        self.assertEqual(info.subject, "会議の件")

    def test_empty_subject(self):
        info = cm.parse_headers(1, b"From: a@b.com\r\n\r\n")
        self.assertEqual(info.subject, "(件名なし)")

    def test_payload_blocks_mentions(self):
        info = cm.parse_headers(1, header("a@b.com", "@everyone 見て"))
        payload = cm.build_discord_payload(info)
        self.assertEqual(payload["allowed_mentions"], {"parse": []})


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state.json"
        self.cfg = cm.load_config(ENV_OK)
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def notify(self, url, payload):
        self.sent.append(payload)

    def test_first_run_sets_baseline_without_notifying(self):
        box = FakeBox({1: header("boss@example.com"), 2: header("boss@example.com")})
        self.assertEqual(cm.run(self.cfg, box, self.state, self.notify), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["last_uid"], 2)

    def test_notifies_only_watched_sender_exact_match(self):
        cm.save_state(self.state, 1, 10)
        box = FakeBox({
            10: header("boss@example.com"),            # 既に見た
            11: header("boss@example.com", "新着"),
            12: header("xboss@example.com"),           # 部分一致は対象外
            13: header("someone@else.com"),
        })
        self.assertEqual(cm.run(self.cfg, box, self.state, self.notify), 1)
        self.assertEqual(self.sent[0]["embeds"][0]["title"], "新着")
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["last_uid"], 13)

    def test_failure_keeps_progress_so_no_duplicate_and_no_loss(self):
        cm.save_state(self.state, 1, 0)
        box = FakeBox({1: header("boss@example.com", "1通目"), 2: header("boss@example.com", "2通目")})

        def flaky(url, payload):
            if payload["embeds"][0]["title"] == "2通目":
                raise RuntimeError("Discord down")
            self.sent.append(payload)

        with self.assertRaises(RuntimeError):
            cm.run(self.cfg, box, self.state, flaky)
        # 1通目は知らせ済みとして進み、2通目は次の回にもう一度試される
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["last_uid"], 1)
        cm.run(self.cfg, box, self.state, self.notify)
        self.assertEqual([p["embeds"][0]["title"] for p in self.sent], ["1通目", "2通目"])

    def test_uidvalidity_change_resets_baseline(self):
        cm.save_state(self.state, 1, 3)
        box = FakeBox({1: header("boss@example.com")}, uidvalidity=2)
        self.assertEqual(cm.run(self.cfg, box, self.state, self.notify), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8")), {"uidvalidity": 2, "last_uid": 1})

    def test_notify_cap(self):
        cm.save_state(self.state, 1, 0)
        box = FakeBox({i: header("boss@example.com") for i in range(1, 16)})
        cm.run(self.cfg, box, self.state, self.notify)
        self.assertEqual(len(self.sent), cm.MAX_NOTIFY_PER_RUN)
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["last_uid"], cm.MAX_NOTIFY_PER_RUN)

    def test_broken_state_file_fails(self):
        self.state.write_text('{"last_uid": "x"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            cm.run(self.cfg, FakeBox({}), self.state, self.notify)


if __name__ == "__main__":
    unittest.main()
