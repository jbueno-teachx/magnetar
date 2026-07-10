# SPDX-License-Identifier: CC0-1.0
"""Allow ``python -m magnetar`` to launch the simulator."""

from magnetar.app import main

if __name__ == "__main__":
    raise SystemExit(main())
