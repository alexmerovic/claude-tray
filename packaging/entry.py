# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""Ponto de entrada do executavel. O PyInstaller roda este arquivo como
script solto, onde o `from .cli import main` do __main__.py quebraria."""

from claude_tray.cli import main

raise SystemExit(main())
