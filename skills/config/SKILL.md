---
description: Show or change email-mode settings (recipient address, polling on/off and intervals, whether terminal turns are summarized by email).
argument-hint: "[key=value ...]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/email_mode.py:*)
---

# email-mode config

Requested change: `$ARGUMENTS`

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/email_mode.py" config [key=value ...]` (no pairs = show current settings).
Translate plain-English requests into keys:

| key | default | meaning |
|---|---|---|
| `to` | (unset) | address emails go to; only replies from it are obeyed |
| `poll_enabled` | `true` | `false` turns reply polling off entirely (summaries are still sent) |
| `poll_min_minutes` | `1` | poll every N minutes during the first window after any activity (reply, terminal message, summary sent); the gap grows by N each window |
| `poll_window_minutes` | `60` | length of each window (default: every 1 min for an hour, every 2 min the next hour, ...) |
| `poll_max_minutes` | `15` | longest gap between polls; set equal to `poll_min_minutes` for a fixed rate |
| `stop_after_hours` | `24` | then pause polling until the user types in the terminal (`0` = never pause) |
| `summarize_terminal_turns` | `true` | `false` = only email summaries for work triggered by an email reply |

Settings are global and apply immediately, including to running sessions. Show the resulting config briefly.
