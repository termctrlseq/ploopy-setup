#!/usr/bin/python3

#
# ~/.config/ploopy/update_kb_dev.py
#

import logging
import os
import signal
from pathlib import Path

logger = logging.getLogger(Path(__file__).name)
ploopy_log = "/home/anton/.config/ploopy/ploopy.log"
logging.basicConfig(
    filename=ploopy_log,
    filemode="a",
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    encoding="utf-8",
    level=logging.DEBUG,
)

PID_FILE = Path("/run/user/1000/ploopy.pid")
EXPECTED_CMD = "/home/anton/.config/ploopy/ploo.py\x00"


def get_pidfd():
    try:
        pid = int(PID_FILE.read_text().strip())
        if pid <= 0:
            return None

        # Verify process command
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        cmd = cmdline.split(b"\0", 1)[1].decode()
        logger.debug(f"{pid=} {cmd=}")

        if cmd != EXPECTED_CMD:
            return None

        return os.pidfd_open(pid)

    except (ValueError, OSError, UnicodeDecodeError):
        return None


pidfd = get_pidfd()

if pidfd is not None:
    try:
        logger.debug("Raising SIGUSR1: keyboards added/removed")
        signal.pidfd_send_signal(pidfd, signal.SIGUSR1)
    finally:
        os.close(pidfd)
