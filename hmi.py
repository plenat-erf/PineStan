#!/usr/bin/env python3
"""Terminal HMI for the distillation simulator."""

from __future__ import annotations

import curses
import json
import socket
import time
from typing import Any

HOST = "127.0.0.1"
PORT = 8765

CONTROL_ORDER = [
    ("feed_valve", "Feed Valve"),
    ("feed_pump_speed", "Feed Pump Speed"),
    ("heating_power", "Heater Power"),
    ("cooling_pump_speed", "Cooling Pump Speed"),
]


def send_cmd(cmd: dict[str, Any], timeout_s: float = 1.2) -> dict[str, Any]:
    payload = (json.dumps(cmd) + "\n").encode("utf-8")
    with socket.create_connection((HOST, PORT), timeout=timeout_s) as sock:
        sock.sendall(payload)
        buffer = b""
        while not buffer.endswith(b"\n"):
            block = sock.recv(4096)
            if not block:
                break
            buffer += block
    if not buffer:
        return {"ok": False, "error": "No response from simulator"}
    return json.loads(buffer.decode("utf-8"))


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def draw_screen(stdscr: Any, selected: int, controls: dict[str, float], state: dict[str, Any], status: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    title = "Distillation HMI (TUI)"
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)

    pfd = "Feedstock Tank -> Valve -> Feed Pump -> Distillation Flask -> Column -> Collection Tank"
    cline = "Water Intake -> Cooling Pump -> Column Cooling Sleeve -> Waste Outlet"
    stdscr.addstr(2, 2, pfd[: w - 4])
    stdscr.addstr(3, 2, cline[: w - 4])

    stdscr.addstr(5, 2, "Controls (UP/DOWN select, LEFT/RIGHT adjust, Q quit):", curses.A_UNDERLINE)
    for idx, (key, label) in enumerate(CONTROL_ORDER):
        marker = ">" if idx == selected else " "
        value = controls.get(key, 0.0)
        stdscr.addstr(6 + idx, 2, f"{marker} {label:<22} {value * 100:6.1f}%")

    row = 11
    stdscr.addstr(row, 2, "Live Sensors:", curses.A_UNDERLINE)
    row += 1
    sensors = [
        f"Feedstock level:          {state.get('feedstock_level_l', 0.0):8.1f} L",
        f"Feed line flow:           {state.get('feed_line_flow_lpm', 0.0):8.2f} L/min",
        f"Flask level:              {state.get('flask_level_l', 0.0):8.1f} L",
        f"Flask temperature:        {state.get('flask_temp_c', 0.0):8.2f} C",
        f"Flask SG:                 {state.get('flask_specific_gravity', 1.0):8.4f}",
        f"Flask ethanol fraction:   {state.get('flask_ethanol_frac', 0.0) * 100:8.2f}%",
        f"Vaporization rate:        {state.get('vaporization_rate_lpm', 0.0):8.2f} L/min",
        f"Cooling inlet temp:       {state.get('cooling_inlet_temp_c', 0.0):8.2f} C",
        f"Cooling outlet temp:      {state.get('cooling_outlet_temp_c', 0.0):8.2f} C",
        f"Cooling flow:             {state.get('cooling_flow_lpm', 0.0):8.2f} L/min",
        f"Collection level:         {state.get('collection_level_l', 0.0):8.1f} L",
        f"Collection temperature:   {state.get('collection_temp_c', 0.0):8.2f} C",
    ]
    for line in sensors:
        if row >= h - 3:
            break
        stdscr.addstr(row, 2, line[: w - 4])
        row += 1

    stdscr.addstr(h - 2, 2, f"Status: {status}"[: w - 4], curses.A_DIM)
    stdscr.refresh()


def run_hmi(stdscr: Any) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    selected = 0
    status = "Connecting to simulator..."
    controls: dict[str, float] = {}
    state: dict[str, Any] = {}
    last_refresh = 0.0

    while True:
        now = time.time()
        if now - last_refresh >= 1.0:
            try:
                response = send_cmd({"cmd": "get_state"})
                if response.get("ok"):
                    controls = response.get("controls", controls)
                    state = response.get("state", state)
                    status = "Connected"
                else:
                    status = f"Simulator error: {response.get('error', 'unknown')}"
            except Exception as exc:
                status = f"Disconnected: {exc}"
            last_refresh = now

        draw_screen(stdscr, selected, controls, state, status)
        key = stdscr.getch()
        if key == -1:
            continue

        if key in (ord("q"), ord("Q")):
            return
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(CONTROL_ORDER)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(CONTROL_ORDER)
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
            control_key = CONTROL_ORDER[selected][0]
            step = 0.03 if key == curses.KEY_RIGHT else -0.03
            current = controls.get(control_key, 0.0)
            controls[control_key] = clamp01(current + step)
            try:
                ack = send_cmd({"cmd": "set_controls", "controls": {control_key: controls[control_key]}})
                if ack.get("ok"):
                    status = f"Updated {control_key} to {controls[control_key] * 100:.1f}%"
                else:
                    status = f"Control write failed: {ack.get('error', 'unknown')}"
            except Exception as exc:
                status = f"Control write failed: {exc}"


def main() -> None:
    curses.wrapper(run_hmi)


if __name__ == "__main__":
    main()
