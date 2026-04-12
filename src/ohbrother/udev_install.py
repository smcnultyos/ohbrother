"""Install the udev rules file for rootless USB access.

Run as root (or with sudo):
    sudo ohbrother-install-udev
"""

from __future__ import annotations

import importlib.resources
import os
import shutil
import subprocess
import sys

UDEV_DIR = "/etc/udev/rules.d"
RULES_NAME = "99-brother-ql.rules"


def main() -> None:
    if os.geteuid() != 0:
        print("Error: must be run as root.", file=sys.stderr)
        print("  sudo ohbrother-install-udev", file=sys.stderr)
        sys.exit(1)

    src = importlib.resources.files("ohbrother") / "udev" / RULES_NAME
    dst = os.path.join(UDEV_DIR, RULES_NAME)

    os.makedirs(UDEV_DIR, exist_ok=True)
    with importlib.resources.as_file(src) as path:
        shutil.copy(str(path), dst)

    print(f"Installed {dst}")

    subprocess.run(["udevadm", "control", "--reload-rules"], check=False)
    subprocess.run(["udevadm", "trigger"], check=False)
    print("udev rules reloaded. Reconnect your printer if it was already plugged in.")
