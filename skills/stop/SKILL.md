---
description: Stop email mode for this session. Sends a closing email, cancels reply polling and closes the email-mode session.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/email_mode.py:*), mcp__claude_ai_Gmail__send_message, CronDelete, CronList
---

# Stop email-mode

1. Find this session's id (`em-xxxx`) from the conversation, or run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/email_mode.py" status`.
2. Send a short closing email with `mcp__claude_ai_Gmail__send_message` on the same thread (`to`, `subject`,
   `replyThreadId` as used before): "Email mode stopped. Replies to this thread are no longer read."
   followed by `-- email-mode em-<id>`.
3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/email_mode.py" stop --id <id>`.
4. Delete the poll job with `CronDelete`. If the printed cron id isn't a usable job id, use `CronList` and
   delete the job whose prompt starts with `[em-poll <id>]`.
5. Confirm to the user in one line.
