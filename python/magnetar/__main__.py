"""Allow ``python -m magnetar`` to launch the simulator."""

from magnetar.app import main

if __name__ == "__main__":
    raise SystemExit(main())
