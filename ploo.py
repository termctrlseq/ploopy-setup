#!/usr/bin/env python3

#
# ~/.config/ploopy/ploo.py
#

import asyncio
import logging
import math
import os
import signal
from typing import Any

from evdev import InputDevice, UInput, list_devices
from evdev import ecodes as e

logger = logging.getLogger(os.path.basename(__file__))

keys: tuple[int, ...] = (
    e.KEY_LEFTALT,
    e.KEY_RIGHTALT,
    e.KEY_LEFTCTRL,
    e.KEY_RIGHTCTRL,
)
keyboards: list[InputDevice] = []
scroll_lock: bool = True
update_task = None


def factor(points: list[float], step: int, speed: float):
    i = int(speed // step)
    if i >= len(points) - 1:
        return points[-1]

    t = (speed - i * step) / step
    return points[i] + t * (points[i + 1] - points[i])


def get_device(name: str) -> InputDevice:
    for d in list_devices():
        try:
            dev = InputDevice(d)
        except OSError:
            continue

        if dev.name == name:
            return dev

        dev.close()
    raise RuntimeError(f"Could not find input device: {name}")


def get_keyboards() -> None:
    for kb in keyboards:
        kb.close()

    keyboards.clear()

    for path in list_devices():
        try:
            keyboard = InputDevice(path)

            for key in keys:
                if key in keyboard.capabilities().get(e.EV_KEY, []):
                    keyboards.append(keyboard)
                    break

            else:
                keyboard.close()

        except (OSError, SystemError):
            continue


def create_pid_file() -> None:
    pid_file = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "ploopy.pid"
    )
    with open(pid_file, "w") as f:
        f.write(f"{os.getpid()}\n")


def key_down(_keys: tuple[int, ...], _keyboards: list[InputDevice]) -> bool:
    for keyboard in _keyboards[:]:
        try:
            active_keys = keyboard.active_keys()

        except (OSError, SystemError):
            _keyboards.remove(keyboard)
            keyboard.close()
            continue

        if any(key in _keys for key in active_keys):
            return True

    return False


async def handle_mouse_events(
    _keys: tuple[int, ...], _keyboards: list[InputDevice]
) -> None:
    ploopy_mouse = "Ploopy Corporation Ploopy Nano 2 Trackball Mouse"
    points = [0.1, 0.3, 0.6, 1.0, 1.5]
    step = 5

    mouse = get_device(ploopy_mouse)

    create_pid_file()
    logger.debug(f"Created pid file; Starting '{ploopy_mouse}' handling")

    with (
        UInput.from_device(mouse, name="ploopy-accel") as ui,
        mouse.grab_context(),
    ):
        dx = dy = 0
        rx = ry = 0.0  # sub-pixel remainders
        last_t = None

        async for ev in mouse.async_read_loop():
            ctrl_key = key_down(_keys, _keyboards)
            move_pointer = ctrl_key if scroll_lock else not ctrl_key
            if ev.type == e.EV_REL and ev.code == e.REL_X:
                if move_pointer:
                    dx += ev.value
                else:
                    ui.write(e.EV_REL, e.REL_HWHEEL_HI_RES, ev.value)

            elif ev.type == e.EV_REL and ev.code == e.REL_Y:
                if move_pointer:
                    dy += ev.value
                else:
                    ui.write(e.EV_REL, e.REL_WHEEL_HI_RES, ev.value)

            elif ev.type == e.EV_SYN and ev.code == e.SYN_DROPPED:
                dx = dy = 0
                rx = ry = 0.0
                last_t = ev.timestamp()

            elif ev.type == e.EV_SYN and ev.code == e.SYN_REPORT:
                t = ev.timestamp()

                if (dx or dy) and last_t:
                    dt = max((t - last_t) * 1000, 1.0)  # ms
                    f = factor(points, step, math.hypot(dx, dy) / dt)

                    rx += dx * f
                    ry += dy * f
                    ox, oy = int(rx), int(ry)
                    rx -= ox
                    ry -= oy

                    if ox:
                        ui.write(e.EV_REL, e.REL_X, ox)
                    if oy:
                        ui.write(e.EV_REL, e.REL_Y, oy)

                last_t = t
                dx = dy = 0
                ui.syn()

            else:
                ui.write(ev.type, ev.code, ev.value)


async def handle_button_events() -> None:
    ploopy_button = "Ploopy Corporation Ploopy Nano 2 Trackball"
    button = get_device(ploopy_button)

    global scroll_lock

    logger.debug(f"Starting '{ploopy_button}' handling")
    with button.grab_context():
        async for ev in button.async_read_loop():
            if (
                ev.type == e.EV_KEY
                and ev.code == e.KEY_SCROLLLOCK
                and ev.value == 1
            ):
                scroll_lock = not scroll_lock


def schedule_update(signum: int, stack_frame: Any):  # noqa: ARG001
    global update_task
    logger.debug("Scheduling update")
    if update_task is not None:
        logger.debug("Task is already running")
        return

    update_task = asyncio.create_task(update_kb_dev())


async def update_kb_dev() -> None:
    global update_task

    logger.debug("Updating keyboards")
    await asyncio.sleep(0.2)
    get_keyboards()
    update_task = None


async def main() -> None:
    get_keyboards()
    signal.signal(signal.SIGUSR1, schedule_update)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(handle_mouse_events(keys, keyboards))
        tg.create_task(handle_button_events())


if __name__ == "__main__":
    config_dir = os.environ.get(
        "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
    )
    ploopy_log = os.path.join(config_dir, "ploopy/ploopy.log")
    logging.basicConfig(
        filename=ploopy_log,
        filemode="a",
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        encoding="utf-8",
        level=logging.DEBUG,
    )

    asyncio.run(main())
