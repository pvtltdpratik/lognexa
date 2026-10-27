"""Entry point for the standalone Windows build of the agent.

PyInstaller bundles this script, the lognexa_agent package and a Python
interpreter into one lognexa-agent.exe, so target machines need no Python:

    pyinstaller --onefile --name lognexa-agent --console agent/launcher.py
"""

import sys

from lognexa_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
