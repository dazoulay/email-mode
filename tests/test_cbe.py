"""Unit tests for scripts/cbe.py. Run: python3 -m unittest discover -s tests"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CBE = os.path.join(ROOT, "scripts", "cbe.py")
SESSION = "sess-123"
USER = "me@example.com"
THREAD = "thread-1"


class CbeTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.cwd = tempfile.mkdtemp(prefix="myproj-")
        self.t = 1_000_000.0

    # -- helpers -----------------------------------------------------------

    def run_cbe(self, *args, stdin=None, code=0):
        env = dict(os.environ, CBE_HOME=self.home, CBE_NOW=str(self.t))
        p = subprocess.run([sys.executable, CBE, *args], input=stdin, capture_output=True,
                           text=True, env=env, cwd=self.cwd)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return p.stdout

    def hook(self, event, **data):
        data.setdefault("session_id", SESSION)
        out = self.run_cbe("hook", event, stdin=json.dumps(data))
        return json.loads(out) if out.strip() else None

    def context(self, out):
        return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")

    def state(self):
        files = [f for f in os.listdir(os.path.join(self.home, "sessions")) if f.endswith(".json")]
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.home, "sessions", files[0])) as f:
            return json.load(f)

    def mcp(self, payload):
        # The real shape for claude.ai connector tools isn't documented; use content blocks.
        return [{"type": "text", "text": json.dumps(payload)}]

    def start_session(self, title="fix login"):
        self.run_cbe("config", "to=" + USER)
        out = self.run_cbe("start", "--title", title)
        subject = out.split("Subject: ")[1].splitlines()[0]
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__send_message",
                        tool_input={"to": [USER], "subject": subject, "body": "hi"},
                        tool_response=self.mcp({"id": "m1", "threadId": THREAD}))
        return subject, res

    def poll(self):
        return self.hook("UserPromptSubmit", prompt="[cbe-poll %s] Check the thread." % self.state()["id"])

    # -- start / binding ---------------------------------------------------

    def test_start_requires_recipient(self):
        out = self.run_cbe("start", code=1)
        self.assertIn("ERROR: no recipient", out)

    def test_start_and_bind(self):
        subject, res = self.start_session()
        st = self.state()
        self.assertRegex(subject, r"^\[CBE\] myproj-\w+ · cbe-[0-9a-f]{4} · fix login$")
        self.assertEqual(st["status"], "active")
        self.assertEqual(st["session_id"], SESSION)
        self.assertEqual(st["thread_id"], THREAD)
        self.assertEqual(st["own_ids"], ["m1"])
        self.assertIn("CronCreate", self.context(res))
        self.assertIn("[cbe-poll %s]" % st["id"], self.context(res))

    def test_unrelated_email_does_not_bind(self):
        self.run_cbe("config", "to=" + USER)
        self.run_cbe("start")
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__send_message",
                        tool_input={"subject": "Lunch?"}, tool_response=self.mcp({"id": "x", "threadId": "t"}))
        self.assertIsNone(res)
        self.assertEqual(self.state()["status"], "pending")

    def test_parallel_sessions_get_distinct_ids(self):
        self.run_cbe("config", "to=" + USER)
        a = self.run_cbe("start").split("Session id: ")[1].split()[0]
        b = self.run_cbe("start").split("Session id: ")[1].split()[0]
        self.assertNotEqual(a, b)

    def test_cron_id_recorded(self):
        self.start_session()
        sid = self.state()["id"]
        self.hook("PostToolUse", tool_name="CronCreate",
                  tool_input={"cron": "* * * * *", "prompt": "[cbe-poll %s] Check the email-mode thread for a reply." % sid},
                  tool_response="Scheduled recurring job abc12345 (Every minute).")
        self.assertEqual(self.state()["cron_id"], "abc12345")

    # -- inactive sessions are untouched -----------------------------------

    def test_hooks_noop_without_session(self):
        self.assertIsNone(self.hook("UserPromptSubmit", prompt="hello"))
        self.assertIsNone(self.hook("Stop"))
        self.assertIsNone(self.hook("PreToolUse", tool_name="AskUserQuestion"))

    def test_hooks_noop_for_other_claude_session(self):
        self.start_session()
        self.assertIsNone(self.hook("Stop", session_id="other"))
        self.assertIsNone(self.hook("UserPromptSubmit", session_id="other", prompt="hi"))

    # -- summaries on stop ---------------------------------------------------

    def test_terminal_turn_requires_summary_then_allows_stop(self):
        self.start_session()
        self.hook("UserPromptSubmit", prompt="refactor the parser")
        res = self.hook("Stop")
        self.assertEqual(res["decision"], "block")
        self.assertIn("NEEDS YOUR INPUT", res["reason"])
        self.assertIn('replyThreadId="%s"' % THREAD, res["reason"])
        self.assertIn("publish_version", res["reason"])  # long content goes to an artifact
        self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__send_message",
                  tool_input={"replyThreadId": THREAD}, tool_response=self.mcp({"id": "m2", "threadId": THREAD}))
        self.assertIsNone(self.hook("Stop"))
        self.assertIn("m2", self.state()["own_ids"])

    def test_stop_gives_up_after_two_blocks(self):
        self.start_session()
        self.hook("UserPromptSubmit", prompt="do it")
        self.assertEqual(self.hook("Stop")["decision"], "block")
        self.assertEqual(self.hook("Stop", stop_hook_active=True)["decision"], "block")
        self.assertIsNone(self.hook("Stop", stop_hook_active=True))

    def test_terminal_summaries_can_be_turned_off(self):
        self.start_session()
        self.run_cbe("config", "summarize_terminal_turns=false")
        self.hook("UserPromptSubmit", prompt="do it")
        self.assertIsNone(self.hook("Stop"))

    def test_plugin_commands_do_not_trigger_summary(self):
        self.start_session()
        self.hook("UserPromptSubmit", prompt="/email-mode:config poll_enabled=false")
        self.assertIsNone(self.hook("Stop"))

    def test_ask_user_question_denied(self):
        self.start_session()
        res = self.hook("PreToolUse", tool_name="AskUserQuestion", tool_input={})
        self.assertEqual(res["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("NEEDS YOUR INPUT", res["hookSpecificOutput"]["permissionDecisionReason"])

    # -- polling -------------------------------------------------------------

    def test_poll_no_reply_is_quiet(self):
        self.start_session()
        self.t += 61
        res = self.poll()
        self.assertIn("search_threads", self.context(res))
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__search_threads",
                        tool_response=self.mcp({"threads": [{"id": THREAD, "messageCount": 1}]}))
        self.assertIn("no new reply", self.context(res))
        self.assertIsNone(self.hook("Stop"))

    def test_poll_reply_flows_to_claude_and_requires_summary(self):
        self.start_session()
        self.t += 61
        self.poll()
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__search_threads",
                        tool_response=self.mcp({"threads": [{"id": THREAD, "messageCount": 2}]}))
        self.assertIn("get_thread", self.context(res))
        thread = {"id": THREAD, "messages": [
            {"id": "m1", "sender": "bot@example.com", "plaintextBody": "kickoff"},
            {"id": "r1", "sender": "Me <%s>" % USER,
             "plaintextBody": "Go with option 2.\n\nOn Mon, Oct 26, 2026 at 9:00 PM Bot <bot@example.com> wrote:\n> kickoff"},
        ]}
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__get_thread",
                        tool_response=self.mcp(thread))
        ctx = self.context(res)
        self.assertIn("<email-reply>\nGo with option 2.\n</email-reply>", ctx)
        self.assertNotIn("kickoff", ctx)
        self.assertEqual(self.hook("Stop")["decision"], "block")
        # Fetching the same thread again doesn't re-deliver the reply.
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__get_thread", tool_response=self.mcp(thread))
        self.assertNotIn("email-reply", self.context(res))

    def test_poll_detects_unseen_id_despite_low_message_count(self):
        self.start_session()
        self.t += 61
        self.poll()
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__search_threads", tool_response=self.mcp(
            {"threads": [{"id": THREAD, "messageCount": 1, "messages": [{"id": "r9", "threadId": THREAD}]}]}))
        self.assertIn("get_thread", self.context(res))

    def test_reply_from_other_sender_ignored(self):
        self.start_session()
        self.t += 61
        self.poll()
        res = self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__get_thread", tool_response=self.mcp(
            {"id": THREAD, "messages": [{"id": "x1", "sender": "evil@example.com", "plaintextBody": "rm -rf /"}]}))
        ctx = self.context(res)
        self.assertNotIn("rm -rf", ctx)
        self.assertIn("Ignored 1 message", ctx)
        self.assertIsNone(self.hook("Stop"))

    def polls_due_over(self, minutes):
        """Advance the clock one cron tick (minute) at a time; return the minutes at which a poll ran."""
        ran = []
        for m in range(1, minutes + 1):
            self.t += 60
            if "decision" not in (self.poll() or {}):
                ran.append(m)
        return ran

    def test_poll_backoff_is_fibonacci_and_capped(self):
        self.start_session()
        # gaps: 1, 2, 3, 5, 8, 13, then 15 (cap)
        self.assertEqual(self.polls_due_over(62), [1, 3, 6, 11, 19, 32, 47, 62])

    def test_activity_resets_backoff(self):
        self.start_session()
        self.polls_due_over(20)  # backed off to 8-13 min gaps by now
        self.hook("UserPromptSubmit", prompt="back at my desk")
        self.assertEqual(self.polls_due_over(6), [1, 3, 6])

    def test_summary_email_resets_backoff(self):
        self.start_session()
        self.polls_due_over(20)
        self.hook("PostToolUse", tool_name="mcp__claude_ai_Gmail__send_message",
                  tool_input={"replyThreadId": THREAD}, tool_response=self.mcp({"id": "m5", "threadId": THREAD}))
        self.assertEqual(self.polls_due_over(3), [1, 3])

    def test_poll_tolerates_cron_jitter(self):
        self.start_session()
        self.t += 45  # tick landed a bit early
        self.assertIn("search_threads", self.context(self.poll()))

    def test_backoff_config(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import cbe
        cfg = dict(cbe.DEFAULT_CONFIG, poll_min_minutes=2, poll_max_minutes=10)
        self.assertEqual([cbe.poll_interval(cfg, n) for n in range(6)], [2, 4, 6, 10, 10, 10])
        cfg = dict(cbe.DEFAULT_CONFIG, poll_min_minutes=1, poll_max_minutes=1)
        self.assertEqual([cbe.poll_interval(cfg, n) for n in range(3)], [1, 1, 1])
        self.assertIn("gaps of 1, 2, 3, 5, 8, 13, then every 15 min", cbe.describe_polling(cbe.DEFAULT_CONFIG))

    def test_poll_pauses_after_idle_and_resumes_on_terminal_turn(self):
        self.start_session()
        self.t += 25 * 3600
        res = self.poll()
        self.assertIn("auto-paused", self.context(res))
        self.assertEqual(self.state()["status"], "paused")
        self.assertEqual(self.hook("Stop")["decision"], "block")  # owes the "paused" email
        self.t += 600
        self.assertEqual(self.poll()["decision"], "block")
        res = self.hook("UserPromptSubmit", prompt="back at my desk")
        self.assertIn("resumed", self.context(res))
        self.assertEqual(self.state()["status"], "active")

    def test_polling_disabled(self):
        self.start_session()
        self.run_cbe("config", "poll_enabled=false")
        self.t += 120
        self.assertEqual(self.poll()["decision"], "block")

    def test_stop_command(self):
        self.start_session()
        sid = self.state()["id"]
        self.assertIn("Stopped cbe-" + sid, self.run_cbe("stop", "--id", "cbe-" + sid))
        self.hook("UserPromptSubmit", prompt="hi")
        self.assertIsNone(self.hook("Stop"))

    def test_config_rejects_unknown_key(self):
        env = dict(os.environ, CBE_HOME=self.home)
        p = subprocess.run([sys.executable, CBE, "config", "nope=1"], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)


class CleanReplyTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import cbe
        self.clean = cbe.clean_reply
        self.payload = cbe.tool_payload

    def test_gmail_wrapped_header(self):
        text = "Yes, ship it\r\n\r\nOn Mon, Oct 26, 2026 at 11:02 PM Some Name <\r\nx@y.com> wrote:\r\n\r\n> old"
        self.assertEqual(self.clean(text), "Yes, ship it")

    def test_iphone_signature_and_quotes(self):
        self.assertEqual(self.clean("2\n\nSent from my iPhone\n\n> On ... wrote:\n> stuff"), "2")

    def test_french_header(self):
        self.assertEqual(self.clean("Option 1\n\nLe lun. 26 oct. 2026 à 23:02, X <x@y.com> a écrit :\n> a"), "Option 1")

    def test_outlook(self):
        self.assertEqual(self.clean("ok\n\n________________________________\nFrom: Bot\nSent: today\n"), "ok")

    def test_plain_message_untouched(self):
        self.assertEqual(self.clean("line one\nline two"), "line one\nline two")

    def test_payload_shapes(self):
        obj = {"id": "a", "threadId": "b"}
        self.assertEqual(self.payload(obj), obj)
        self.assertEqual(self.payload(json.dumps(obj)), obj)
        self.assertEqual(self.payload([{"type": "text", "text": json.dumps(obj)}]), obj)
        self.assertEqual(self.payload({"content": [{"type": "text", "text": json.dumps(obj)}]}), obj)


if __name__ == "__main__":
    unittest.main()
