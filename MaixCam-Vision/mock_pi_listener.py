#!/usr/bin/env python3
"""Validate simulated vision UART commands against the Pi receiver contract."""

import sys
import time


ALLOWED_COMMANDS = {
    "STRAFE_LEFT",
    "STRAFE_RIGHT",
    "ALIGNED_STOP",
    "NO_TARGET",
}
MIN_RATE_HZ = 5.0


def main():
    started = time.monotonic()
    commands = []

    for raw_line in sys.stdin:
        command = raw_line.rstrip("\r\n")
        if command not in ALLOWED_COMMANDS:
            print(f"FAIL: invalid UART command: {command!r}")
            return 1
        commands.append(command)

    elapsed = time.monotonic() - started
    rate_hz = (len(commands) - 1) / elapsed if elapsed > 0 else 0.0

    if len(commands) < 6:
        print(f"FAIL: expected at least 6 commands, received {len(commands)}")
        return 1
    if rate_hz < MIN_RATE_HZ:
        print(f"FAIL: command rate {rate_hz:.1f} Hz is below {MIN_RATE_HZ:.1f} Hz")
        return 1

    print(f"PASS: {len(commands)} valid UART commands at {rate_hz:.1f} Hz")
    print("PASS: pipe closed; mock receiver safe-stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())