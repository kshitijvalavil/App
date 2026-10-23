#!/usr/bin/env python3
"""Launch the token usage dashboard and open it in your browser.

Run on your OWN machine (where ~/.claude/projects lives):

    python run_dashboard.py

Then it opens http://127.0.0.1:5000/tokens automatically.
"""

import os
import threading
import webbrowser

from MyAPP import app

PORT = int(os.environ.get("PORT", "5000"))
URL = f"http://127.0.0.1:{PORT}/tokens"


def main():
    print(f"\n  Claude token dashboard → {URL}")
    print("  Reading logs from:", os.environ.get("CLAUDE_LOGS_DIR") or "~/.claude/projects")
    print("  Press Ctrl+C to stop.\n")
    threading.Timer(1.0, lambda: webbrowser.open(URL)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
