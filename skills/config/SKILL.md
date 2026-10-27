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
| `poll_min_minutes` | `1` | first poll this many minutes after any activity (reply, terminal message, summary sent) |
| `poll_max_minutes` | `15` | gaps grow by Fibonacci (1, 2, 3, 5, 8, 13...) up to this; equal to min = no backoff |
| `stop_after_hours` | `24` | then pause polling until the user types in the terminal (`0` = never pause) |
| `summarize_terminal_turns` | `true` | `false` = only email summaries for work triggered by an email reply |

Settings are global and apply immediately, including to running sessions. Show the resulting config briefly.
