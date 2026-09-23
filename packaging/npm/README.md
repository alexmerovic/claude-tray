# Claude Tray

**By Svatka Technologies™**. Your Claude Code 5-hour usage window, live in the Windows system tray.
Two icons next to the clock: how much of your quota is gone, and how much of the window has passed.

```
npx @svatka/claude-tray              # start the meter in the tray
npx @svatka/claude-tray --status     # print the current reading
npx @svatka/claude-tray --autostart  # start with Windows
```

On first run it downloads the official `ClaudeTray.exe` from the GitHub release
and verifies its SHA-256 before running it. Nothing runs at `npm install` time.

Prefer a regular installer? Grab `ClaudeTray-Setup.exe` from
[the releases page](https://github.com/alexmerovic/claude-tray/releases).

## License

Free to use. © 2026 Svatka Technologies™ (Alex Merovic). All rights reserved.
Modifying, copying or redistributing it is not permitted. See [LICENSE](LICENSE).

Not affiliated with Anthropic. "Claude" is a trademark of Anthropic.
