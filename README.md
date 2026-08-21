# claude-tray

**Your Claude Code 5-hour usage window, live in the system tray.** Two small icons next to the clock. No window, no overlay, nothing flying across your screen.

![Two icons in the tray](docs/two-icons.png)

The left icon is **how much of your quota is spent**. The right one is **how much of the window has elapsed**. What you actually read is neither one alone — it is the **gap between them**.

*[Leia em português](README.pt-BR.md)*

---

## Read this first: it reads your credentials file

This tool reads `~/.claude/.credentials.json` — the same OAuth token Claude Code itself stores. You should be suspicious of any program that does that, including this one. So here is exactly what happens, and the whole thing is 170 lines you can read yourself in [`usage_api.py`](src/claude_tray/usage_api.py):

- **`GET` only.** One request, no writes, no side effects on your account.
- **Only the `accessToken`**, used only in the `Authorization` header. Never logged, never copied, never written anywhere.
- **The `refreshToken` is never touched.** Refresh tokens tend to be rotating — renewing one from outside could invalidate Claude Code's own session. If the access token is expired, this degrades instead of renewing.
- **Nothing leaves your machine** except that one request to `api.anthropic.com`. No telemetry, no analytics, no server of mine anywhere in the picture.

The token is re-read from disk on every call, so it picks up whatever the CLI refreshed on its own.

---

## How to read the two icons

Usage alone decides nothing: **80% with 3 hours to go and 80% with 5 minutes left are opposite situations.** That is why there are two icons instead of one clever one.

### Both use the same color scale

They measure the same thing — *how much has been consumed*. One consumes quota, the other consumes clock.

| Band | Color | Left icon (quota spent) | Right icon (window elapsed) |
|---|---|---|---|
| Relaxed | 🔵 blue `#0fadd6` | < 30% | more than 3h30 left |
| Fine | 🟢 green | 30–59% | 2h–3h30 left |
| Attention | 🟡 amber | 60–84% | 45min–2h left |
| Critical | 🔴 red | 85% and up | less than 45 min left |
| Idle / stale reading | ⚪ gray | — | — |

### The gap is the signal

![The five scenarios](docs/color-pairs.png)

| You see | It means | Do |
|---|---|---|
| Left hotter than right | Burning quota too fast for the window | **Slow down** — you will hit the wall before the reset |
| Right hotter than left | Quota to spare, clock running out | **Speed up** — unused quota evaporates at the reset |
| Both the same color | Pace matches the window | Carry on |

> **Red on the time icon is not an alarm.** A reset approaching is good news. What should alarm you is the *difference* between the two.

Both rings also fill **clockwise in the same direction** — the right one draws the window *elapsed*, not remaining. A ring that empties while its neighbor fills forces you to mentally invert one of them every time you glance.

Hover either icon for the details: exact reset time, weekly usage, current burn rate in %/h, projection to the end of the window, and how old the reading is.

---

## Install

Requires Python 3.10+ and Windows (see [platform support](#platform-support)).

```bash
uv tool install claude-tray     # or: pipx install claude-tray
claude-tray                     # start it now
claude-tray --autostart         # and every time you log in
```

That is it. If the icons land in the hidden overflow menu, drag them out — or go to **Settings → Personalization → Taskbar → Other system tray icons** and toggle them on.

### Other commands

```bash
claude-tray --status            # is it running? what does the window read?
claude-tray --config            # open the config file in your editor
claude-tray --debug             # run in the foreground, printing every refresh
claude-tray --remove-autostart  # remove it from logon
```

`claude-tray --status --json --offline` returns the same state as machine-readable JSON without touching the network — that is what the plugin hook consumes.

`claude-trayw` is the same program with no console window — that is what autostart registers.

---

## As a Claude Code plugin

If you would rather not think about starting it:

```
/plugin marketplace add alexmerovic/claude-tray
/plugin install claude-tray
```

This adds a `SessionStart` hook that checks the meter when a session opens, plus a `/usage-tray` command that reports the current state in chat.

**The hook speaks only when there is actual news**, which is exactly one case: you installed the plugin but not the meter. It never launches anything on its own — opening a terminal session should not have side effects outside the terminal, and `claude-tray --autostart` already covers "always running", explicitly and once.

If you want it to start the meter for you, the machinery is already in `main()` — change the `return` in `decidir()` ([`hooks/ensure_tray.py`](hooks/ensure_tray.py)) to `"subir"`. The trade-offs are laid out in the docstring.

---

## Configuration

Lives at `~/.claude-tray/config.json` (created on first run, untouched by upgrades). Right-click either icon → **Reload config** applies changes without restarting.

| Key | What it does |
|---|---|
| `intervalo_seg` | Icon redraw cadence. The clock ticks locally and costs nothing. |
| `intervalo_api_seg` | How often the official percentage is fetched. One request each. |
| `stale_seg` | Above this age a reading turns gray: *"I no longer trust this number."* |
| `limiares` | Color band cutoffs. Low cutoffs warn early but leave the icons permanently amber, which turns them into background noise; high cutoffs stay clean but warn you when it is too late to reorganize the window. |
| `cores` | Hex color per band. |
| `icone.arco` | Set `false` to drop the ring and keep just the number — more legible at 16px. |
| `modo_arco` | `uso` (ring follows its own number) or `tempo` (ring carries the clock). |
| `icone_tempo.ativo` | Set `false` for a single icon. |

---

## Where the number comes from

`GET https://api.anthropic.com/api/oauth/usage` — the same route Claude Code's own `/usage` command uses. It returns `five_hour.utilization` (the real percentage), `five_hour.resets_at` (the exact reset instant), and the weekly figures.

**This endpoint is undocumented.** It can change or disappear without notice. When it does, the meter degrades in three steps rather than lying to you:

1. **Live reading** from the API (seconds old)
2. **`cachedUsageUtilization`** from `~/.claude.json`, written by Claude Code itself — no network, but possibly hours old
3. **Last good reading, in gray** — the number is stale and the icon says so

**The route is rate limited.** Hammering it returns HTTP 429 — a handful of `--status` calls in a row is enough. The meter backs off exponentially (60s, doubling up to 15 minutes, or whatever `Retry-After` says) and serves the cache meanwhile, so it never feeds its own block. Please do not set `intervalo_api_seg` below 60.

A newer reading never gets replaced by an older one, so a network blip cannot silently swap a fresh 63% for a 6-hour-old 36%. And because `resets_at` is an absolute instant, **the clock keeps running with no network at all** — a dead connection freezes the percentage, never the countdown.

### Why not just count tokens?

An earlier version did, summing the `usage` fields in `~/.claude/projects/**/*.jsonl` and dividing by a hand-calibrated limit. Measured against the real thing: the estimate said **26%** when `/usage` said **62%**.

The limit was not mis-tuned — **the token-to-percentage relationship is not stable across windows**, so no calibration would have survived. Token counts are still read for the absolute figures in the tooltip (tokens and estimated US$), because *those* are facts. The percentage is not something you can infer locally.

---

## Why the tray and not the taskbar

Windows 11's taskbar has two regions, and only one accepts third-party content:

| Region | Possible? | Why |
|---|---|---|
| System tray (next to the clock) | Yes | `Shell_NotifyIcon` is alive and supported |
| Deskband / toolbar (a wide strip with text) | No | Win11 rewrote the taskbar in XAML and removed COM deskbands |

Restoring deskbands requires ExplorerPatcher or StartAllBack — a system-level hack, deliberately out of scope.

Windows cannot draw *text* in the tray either — it only accepts an `HICON`. So the number is rendered into a bitmap with Pillow on every refresh and converted to an icon. (pystray calls `DestroyIcon` on the previous handle each swap, so there is no GDI handle leak — the classic bug in this category of app.)

---

## Platform support

**Windows** is what this is built and tested on. pystray itself supports macOS and Linux, so the meter would likely run there, but `--autostart` (a shortcut in the Startup folder) and the font lookup are Windows-specific. PRs adding a macOS LaunchAgent or a Linux `.desktop` entry are welcome — `autostart.py` marks exactly where they would go.

## Notes

Code comments are in Brazilian Portuguese — they carry the reasoning behind each trade-off, and translating a thousand lines of them is where nuance goes to die. Everything user-facing is in English.

MIT licensed. Not affiliated with Anthropic.
