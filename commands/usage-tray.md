---
name: usage-tray
description: Show the tray meter status - is it running, is autostart on, and what the current 5h window reads.
---

Run the status command and report the result to the user in their language:

```bash
claude-tray --status
```

Then interpret it for them, in two lines at most:

- If `meter` is `stopped`, tell them the meter is not running and that
  `claude-tray --autostart` registers it at logon (Windows) or `claude-trayw`
  starts it right now.
- If the reading came back unavailable, name the reason from the output
  (`token_expired`, `no_credentials`, `http_401`, network) instead of guessing.
- If it is running and reading fine, state the usage percentage and how the two
  numbers compare: usage far above elapsed-window means slow down, usage far
  below means there is quota that will evaporate at the reset.

Do not offer to change the config unless they ask.
