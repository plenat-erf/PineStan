#!/usr/bin/env python3
"""Tkinter SCADA-style GUI HMI for the distillation simulator."""

from __future__ import annotations

import json
import math
import socket
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

HOST = "127.0.0.1"
PORT = 8765
POLL_MS = 500
DASH_PATTERN = (10, 6)
DASH_CYCLE_PX = sum(DASH_PATTERN)
FLOW_LIMITS = {"feed": 18.0, "vapor": 5.0, "cool": 55.0}

CONTROL_ORDER = [
    ("flask_temp_sp_c", "Flask Temp SP (°C)", 65, 102),
    ("flask_level_sp_l", "Flask Level SP (L)", 20, 230),
]


class HMIClientError(RuntimeError):
    """Raised when simulator communication fails."""


def send_cmd(payload: dict[str, Any], timeout_s: float = 1.5) -> dict[str, Any]:
    message = (json.dumps(payload) + "\n").encode("utf-8")
    with socket.create_connection((HOST, PORT), timeout=timeout_s) as sock:
        sock.sendall(message)
        data = b""
        while not data.endswith(b"\n"):
            block = sock.recv(4096)
            if not block:
                break
            data += block
    if not data:
        raise HMIClientError("No response from simulator")
    return json.loads(data.decode("utf-8"))


class DistillationGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PineStan Distillation SCADA HMI")
        self.root.geometry("1220x760")
        self._maximize_window()

        self.status_var = tk.StringVar(value="Connecting to simulator...")
        self.state: dict[str, float] = {}
        self.controls: dict[str, float] = {k: float(lo) for k, _, lo, _ in CONTROL_ORDER}
        self.flow_offset_px = {"feed": 0.0, "vapor": 0.0, "cool": 0.0}
        self.last_anim_ts = time.time()
        self.updating_scales = False

        self._build_layout()
        self.root.after(200, self.poll_simulator)
        self.root.after(80, self.animate_flows)

    def _maximize_window(self) -> None:
        try:
            self.root.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.root.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        self.root.geometry("1600x900")

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=8)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(container, background="#11151c", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = ttk.Frame(container)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        controls_frame = ttk.LabelFrame(right, text="Setpoints", padding=10)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.scales: dict[str, tk.Scale] = {}
        for row, (key, label, low, high) in enumerate(CONTROL_ORDER):
            ttk.Label(controls_frame, text=label).grid(row=row, column=0, sticky="w")
            scale = tk.Scale(
                controls_frame,
                from_=low,
                to=high,
                orient=tk.HORIZONTAL,
                resolution=1,
                length=240,
                command=lambda val, k=key: self.on_control_change(k, float(val)),
            )
            scale.grid(row=row, column=1, padx=6)
            self.scales[key] = scale

        sensors_frame = ttk.LabelFrame(right, text="Sensors", padding=10)
        sensors_frame.grid(row=1, column=0, sticky="nsew")
        right.rowconfigure(1, weight=1)

        self.sensor_labels: dict[str, ttk.Label] = {}
        sensor_defs = [
            ("feedstock_level_l", "Feedstock Level", "{:.1f} L"),
            ("feed_line_flow_lpm", "Feed Flow", "{:.2f} L/min"),
            ("flask_level_l", "Flask Level", "{:.1f} L"),
            ("flask_temp_c", "Flask Temp", "{:.1f} °C"),
            ("flask_specific_gravity", "Flask SG", "{:.4f}"),
            ("flask_ethanol_frac", "Flask Ethanol", "{:.1f} %"),
            ("vaporization_rate_lpm", "Vaporization", "{:.2f} L/min"),
            ("cooling_inlet_temp_c", "Cooling Inlet", "{:.1f} °C"),
            ("cooling_outlet_temp_c", "Cooling Outlet", "{:.1f} °C"),
            ("cooling_flow_lpm", "Cooling Flow", "{:.2f} L/min"),
            ("collection_level_l", "Collection Level", "{:.1f} L"),
            ("collection_temp_c", "Collection Temp", "{:.1f} °C"),
            ("feed_valve", "Auto Feed Valve", "{:.0f} %"),
            ("feed_pump_speed", "Auto Feed Pump", "{:.0f} %"),
            ("heating_power", "Auto Heater", "{:.0f} %"),
            ("cooling_pump_speed", "Auto Cooling Pump", "{:.0f} %"),
        ]
        self.sensor_formats = {k: fmt for k, _, fmt in sensor_defs}
        for row, (key, label, _) in enumerate(sensor_defs):
            ttk.Label(sensors_frame, text=f"{label}:").grid(row=row, column=0, sticky="w")
            value_label = ttk.Label(sensors_frame, text="--")
            value_label.grid(row=row, column=1, sticky="e")
            self.sensor_labels[key] = value_label

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.draw_process()

    def on_control_change(self, key: str, value: float) -> None:
        if self.updating_scales:
            return
        self.controls[key] = value
        try:
            result = send_cmd({"cmd": "set_controls", "controls": {key: self.controls[key]}})
            if not result.get("ok"):
                self.status_var.set(f"Setpoint write failed: {result.get('error', 'unknown')}")
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(f"Setpoint write failed: {exc}")

    def poll_simulator(self) -> None:
        try:
            result = send_cmd({"cmd": "get_state"})
            if not result.get("ok"):
                raise HMIClientError(result.get("error", "unknown simulator error"))

            self.state = result.get("state", {})
            self.controls = result.get("controls", self.controls)
            self.status_var.set("Connected")

            self.updating_scales = True
            for key, scale in self.scales.items():
                target = int(round(self.controls.get(key, scale.get())))
                if scale.get() != target:
                    scale.set(target)
            self.updating_scales = False

            self.update_sensor_labels()
            self.draw_process()
        except Exception as exc:  # noqa: BLE001
            self.updating_scales = False
            self.status_var.set(f"Disconnected: {exc}")

        self.root.after(POLL_MS, self.poll_simulator)

    def update_sensor_labels(self) -> None:
        for key, label in self.sensor_labels.items():
            val = self.state.get(key, 0.0)
            if key == "flask_ethanol_frac":
                val *= 100.0
            if key in {"feed_valve", "feed_pump_speed", "heating_power", "cooling_pump_speed"}:
                val *= 100.0
            label.configure(text=self.sensor_formats[key].format(val))

    def _advance_offset(self, flow_key: str, flow_lpm: float, dt_s: float) -> None:
        max_flow = FLOW_LIMITS[flow_key]
        flow_frac = max(0.0, min(1.0, flow_lpm / max_flow))
        min_speed_px_s = 2.0
        max_speed_px_s = 68.0
        px_per_s = min_speed_px_s + (max_speed_px_s - min_speed_px_s) * flow_frac
        if flow_lpm <= 0.01:
            px_per_s = 0.0
        self.flow_offset_px[flow_key] = (self.flow_offset_px[flow_key] + (px_per_s * dt_s)) % DASH_CYCLE_PX

    def animate_flows(self) -> None:
        now = time.time()
        dt_s = max(0.01, now - self.last_anim_ts)
        self.last_anim_ts = now

        self._advance_offset("feed", self.state.get("feed_line_flow_lpm", 0.0), dt_s)
        self._advance_offset("vapor", self.state.get("vaporization_rate_lpm", 0.0), dt_s)
        self._advance_offset("cool", self.state.get("cooling_flow_lpm", 0.0), dt_s)

        self.draw_process()
        self.root.after(80, self.animate_flows)

    def tank_level_ratio(self, name: str, cap: float) -> float:
        return max(0.0, min(1.0, self.state.get(name, 0.0) / cap))

    def draw_tank(self, x1: int, y1: int, x2: int, y2: int, ratio: float, label: str, color: str) -> None:
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#d9d9d9", width=2)
        fill_top = y2 - (y2 - y1) * ratio
        self.canvas.create_rectangle(x1 + 2, fill_top, x2 - 2, y2 - 2, fill=color, outline="")
        self.canvas.create_text((x1 + x2) // 2, y1 - 14, text=label, fill="#f0f0f0")
        self.canvas.create_text((x1 + x2) // 2, y2 + 12, text=f"{ratio * 100:.0f}%", fill="#f0f0f0")

    def draw_valve(self, cx: int, cy: int, opening: float) -> None:
        size = 22
        self.canvas.create_line(cx - size, cy - size, cx + size, cy + size, fill="#dddddd", width=3)
        self.canvas.create_line(cx - size, cy + size, cx + size, cy - size, fill="#dddddd", width=3)
        gap = int((1.0 - opening) * 14)
        self.canvas.create_rectangle(cx - 6, cy - gap, cx + 6, cy + gap, fill="#11151c", outline="#11151c")
        color = "#55d06c" if opening > 0.05 else "#d15252"
        state = "OPEN" if opening > 0.05 else "CLOSED"
        self.canvas.create_text(cx, cy + 30, text=f"Valve {state}", fill=color)

    def draw_pump_tacho(self, cx: int, cy: int, speed: float, name: str) -> None:
        r = 35
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#f0f0f0", width=2)
        for deg in range(-120, 121, 40):
            rad = math.radians(deg)
            self.canvas.create_line(
                cx + (r - 5) * math.cos(rad),
                cy + (r - 5) * math.sin(rad),
                cx + r * math.cos(rad),
                cy + r * math.sin(rad),
                fill="#cccccc",
            )
        needle_deg = -120 + 240 * max(0.0, min(1.0, speed))
        rad = math.radians(needle_deg)
        self.canvas.create_line(cx, cy, cx + (r - 7) * math.cos(rad), cy + (r - 7) * math.sin(rad), fill="#ffb347", width=3)
        self.canvas.create_text(cx, cy + 52, text=f"{name} {speed * 100:.0f}%", fill="#f0f0f0")

    def draw_thermometer(self, x: int, y: int, temp_c: float, label: str, max_temp: float = 120.0) -> None:
        h = 120
        w = 20
        self.canvas.create_rectangle(x, y, x + w, y + h, outline="#f0f0f0", width=2)
        ratio = max(0.0, min(1.0, temp_c / max_temp))
        top = y + h - h * ratio
        self.canvas.create_rectangle(x + 2, top, x + w - 2, y + h - 2, fill="#ff7043", outline="")
        self.canvas.create_oval(x - 8, y + h - 16, x + w + 8, y + h + 16, fill="#ff7043", outline="#f0f0f0")
        self.canvas.create_text(x + w // 2, y - 12, text=label, fill="#f0f0f0")
        self.canvas.create_text(x + w // 2, y + h + 28, text=f"{temp_c:.1f}°C", fill="#f0f0f0")

    def draw_pipe(self, points: list[tuple[int, int]], color: str, offset_px: float) -> None:
        flat = [coord for pt in points for coord in pt]
        self.canvas.create_line(*flat, fill="#3c4a5c", width=8, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        self.canvas.create_line(
            *flat,
            fill=color,
            width=4,
            dash=DASH_PATTERN,
            dashoffset=-offset_px,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

    def draw_column_with_jacket(self) -> None:
        # Siemens-like representation: center vapor path with dual cooling jacket returns
        center_x = 745
        top_y = 120
        bottom_y = 345
        left_jacket = 718
        right_jacket = 772

        self.canvas.create_rectangle(left_jacket, top_y, right_jacket, bottom_y, outline="#e9e9e9", width=2)
        self.canvas.create_line(center_x, top_y + 8, center_x, bottom_y - 8, fill="#ffd86b", width=6)
        self.canvas.create_line(left_jacket + 6, top_y + 8, left_jacket + 6, bottom_y - 8, fill="#73d8ff", width=4)
        self.canvas.create_line(right_jacket - 6, top_y + 8, right_jacket - 6, bottom_y - 8, fill="#73d8ff", width=4)
        self.canvas.create_text(center_x, 104, text="Distillation Column + Cooling Jacket", fill="#f0f0f0")

    def draw_process(self) -> None:
        c = self.canvas
        c.delete("all")

        feed_ratio = self.tank_level_ratio("feedstock_level_l", 1000.0)
        flask_ratio = self.tank_level_ratio("flask_level_l", 250.0)
        coll_ratio = self.tank_level_ratio("collection_level_l", 1000.0)

        self.draw_tank(60, 120, 180, 340, feed_ratio, "Feedstock Tank", "#2f9ee3")
        self.draw_valve(235, 230, self.state.get("feed_valve", 0.0))
        self.draw_pump_tacho(320, 230, self.state.get("feed_pump_speed", 0.0), "Feed Pump")

        self.canvas.create_rectangle(420, 140, 560, 340, outline="#f0f0f0", width=2)
        fill_top = 340 - (340 - 140) * flask_ratio
        self.canvas.create_rectangle(422, fill_top, 558, 338, fill="#f3a84e", outline="")
        self.canvas.create_text(490, 126, text="Distillation Flask", fill="#f0f0f0")
        self.draw_thermometer(570, 190, self.state.get("flask_temp_c", 0.0), "Flask Temp")

        self.draw_column_with_jacket()

        self.draw_tank(890, 120, 1010, 340, coll_ratio, "Collection Tank", "#7ad97a")
        self.draw_thermometer(1020, 190, self.state.get("collection_temp_c", 0.0), "Collection Temp", 80.0)

        self.draw_pump_tacho(320, 520, self.state.get("cooling_pump_speed", 0.0), "Cooling Pump")
        self.draw_thermometer(700, 470, self.state.get("cooling_inlet_temp_c", 0.0), "Cooling In", 50.0)
        self.draw_thermometer(790, 470, self.state.get("cooling_outlet_temp_c", 0.0), "Cooling Out", 50.0)

        self.draw_pipe([(180, 230), (213, 230)], "#7ec8ff", self.flow_offset_px["feed"])
        self.draw_pipe([(257, 230), (285, 230)], "#7ec8ff", self.flow_offset_px["feed"])
        self.draw_pipe([(355, 230), (420, 230)], "#7ec8ff", self.flow_offset_px["feed"])
        self.draw_pipe([(560, 180), (745, 180)], "#ffd86b", self.flow_offset_px["vapor"])
        self.draw_pipe([(745, 220), (890, 220)], "#9ff58f", self.flow_offset_px["vapor"])

        self.draw_pipe([(80, 520), (285, 520)], "#73d8ff", self.flow_offset_px["cool"])
        self.draw_pipe([(355, 520), (690, 520), (690, 140), (724, 140)], "#73d8ff", self.flow_offset_px["cool"])
        self.draw_pipe([(355, 520), (800, 520), (800, 140), (766, 140)], "#73d8ff", self.flow_offset_px["cool"])
        self.draw_pipe([(724, 345), (690, 345), (690, 560), (980, 560)], "#73d8ff", self.flow_offset_px["cool"])
        self.draw_pipe([(766, 345), (800, 345), (800, 560), (1060, 560)], "#73d8ff", self.flow_offset_px["cool"])

        self.canvas.create_text(80, 500, text="Water Intake", fill="#d7ecff")
        self.canvas.create_text(1060, 582, text="Waste Water Outlet", fill="#d7ecff")
        self.canvas.create_text(
            540,
            30,
            text="Distillation Process - SCADA Overview",
            fill="#ffffff",
            font=("TkDefaultFont", 14, "bold"),
        )


def main() -> None:
    root = tk.Tk()
    DistillationGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
