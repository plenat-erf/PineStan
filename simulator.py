#!/usr/bin/env python3
"""Plant simulator for a small ethanol distillation process.

Run this process first, then start ``hmi.py`` in a second terminal.
The simulator exposes a tiny JSON-over-TCP API on 127.0.0.1:8765.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from dataclasses import asdict, dataclass

HOST = "127.0.0.1"
PORT = 8765


@dataclass
class Controls:
    feed_valve: float = 0.4
    feed_pump_speed: float = 0.35
    heating_power: float = 0.45
    cooling_pump_speed: float = 0.55

    def clamp(self) -> None:
        for key in ("feed_valve", "feed_pump_speed", "heating_power", "cooling_pump_speed"):
            setattr(self, key, max(0.0, min(1.0, float(getattr(self, key)))))


@dataclass
class ProcessState:
    timestamp: float
    feedstock_level_l: float
    feedstock_ethanol_frac: float
    feed_line_flow_lpm: float
    flask_level_l: float
    flask_temp_c: float
    flask_ethanol_frac: float
    flask_specific_gravity: float
    vaporization_rate_lpm: float
    cooling_inlet_temp_c: float
    cooling_outlet_temp_c: float
    cooling_flow_lpm: float
    collection_level_l: float
    collection_temp_c: float


class PlantSimulator:
    def __init__(self) -> None:
        self.controls = Controls()

        self.feedstock_capacity_l = 1000.0
        self.feedstock_level_l = 1000.0
        self.feedstock_ethanol_frac = 0.12

        self.flask_capacity_l = 250.0
        self.flask_level_l = 70.0
        self.flask_temp_c = 28.0
        self.flask_ethanol_frac = 0.12

        self.collection_capacity_l = 1000.0
        self.collection_level_l = 0.0
        self.collection_temp_c = 25.0

        self.cooling_inlet_temp_c = 25.0
        self.cooling_outlet_temp_c = 26.0
        self.cooling_day_offset_c = 0.0

        self.feed_line_flow_lpm = 0.0
        self.vaporization_rate_lpm = 0.0
        self.cooling_flow_lpm = 0.0

        self.max_feed_flow_lpm = 18.0
        self.max_cooling_flow_lpm = 55.0
        self.max_vaporization_lpm = 5.0

    @staticmethod
    def _mix_fraction(level: float, frac: float, incoming_level: float, incoming_frac: float) -> float:
        total = level + incoming_level
        if total <= 1e-9:
            return frac
        return ((level * frac) + (incoming_level * incoming_frac)) / total

    @staticmethod
    def _specific_gravity(ethanol_frac: float) -> float:
        density_water = 1.0
        density_ethanol = 0.789
        return (1.0 - ethanol_frac) * density_water + ethanol_frac * density_ethanol

    def snapshot(self) -> ProcessState:
        return ProcessState(
            timestamp=time.time(),
            feedstock_level_l=self.feedstock_level_l,
            feedstock_ethanol_frac=self.feedstock_ethanol_frac,
            feed_line_flow_lpm=self.feed_line_flow_lpm,
            flask_level_l=self.flask_level_l,
            flask_temp_c=self.flask_temp_c,
            flask_ethanol_frac=self.flask_ethanol_frac,
            flask_specific_gravity=self._specific_gravity(self.flask_ethanol_frac),
            vaporization_rate_lpm=self.vaporization_rate_lpm,
            cooling_inlet_temp_c=self.cooling_inlet_temp_c,
            cooling_outlet_temp_c=self.cooling_outlet_temp_c,
            cooling_flow_lpm=self.cooling_flow_lpm,
            collection_level_l=self.collection_level_l,
            collection_temp_c=self.collection_temp_c,
        )

    def set_controls(self, updates: dict[str, float]) -> None:
        for key, value in updates.items():
            if hasattr(self.controls, key):
                setattr(self.controls, key, float(value))
        self.controls.clamp()

    def _update_cooling_source(self, dt_s: float) -> None:
        now = time.time()
        day_phase = (now % 86400.0) / 86400.0
        diurnal = 2.3 * math.sin(2.0 * math.pi * (day_phase - 0.25))
        self.cooling_day_offset_c += random.uniform(-0.02, 0.02) * (dt_s / 60.0)
        self.cooling_day_offset_c = max(-1.5, min(1.5, self.cooling_day_offset_c))

        target = 25.0 + diurnal + self.cooling_day_offset_c
        alpha = 1.0 - math.exp(-dt_s / 420.0)
        self.cooling_inlet_temp_c += (target - self.cooling_inlet_temp_c) * alpha

    def step(self, dt_s: float) -> None:
        dt_min = dt_s / 60.0
        self._update_cooling_source(dt_s)

        self.feed_line_flow_lpm = self.max_feed_flow_lpm * self.controls.feed_valve * self.controls.feed_pump_speed
        feed_transfer_l = min(self.feedstock_level_l, self.feed_line_flow_lpm * dt_min)
        free_flask_l = max(0.0, self.flask_capacity_l - self.flask_level_l)
        feed_transfer_l = min(feed_transfer_l, free_flask_l)

        self.feedstock_level_l -= feed_transfer_l
        if feed_transfer_l > 0:
            self.flask_ethanol_frac = self._mix_fraction(
                self.flask_level_l, self.flask_ethanol_frac, feed_transfer_l, self.feedstock_ethanol_frac
            )
            self.flask_level_l += feed_transfer_l

        self.cooling_flow_lpm = self.max_cooling_flow_lpm * self.controls.cooling_pump_speed

        heating_term = 3.9 * self.controls.heating_power
        cooling_term = 1.7 * self.controls.cooling_pump_speed + max(0.0, self.cooling_inlet_temp_c - 25.0) * 0.08
        temp_target = 26.0 + 80.0 * max(0.0, heating_term - cooling_term)
        temp_alpha = 1.0 - math.exp(-dt_s / 200.0)
        self.flask_temp_c += (temp_target - self.flask_temp_c) * temp_alpha

        temp_drive = max(0.0, self.flask_temp_c - 78.0) / 18.0
        ethanol_boost = 0.25 + self.flask_ethanol_frac
        self.vaporization_rate_lpm = min(
            self.max_vaporization_lpm,
            self.controls.heating_power * temp_drive * ethanol_boost * self.max_vaporization_lpm,
        )

        boil_off_l = min(self.flask_level_l, self.vaporization_rate_lpm * dt_min)

        condenser_eff = 0.18 + 0.8 * self.controls.cooling_pump_speed - max(0.0, self.cooling_inlet_temp_c - 25.0) * 0.015
        condenser_eff = max(0.05, min(0.98, condenser_eff))
        condensed_l = boil_off_l * condenser_eff

        collection_free_l = max(0.0, self.collection_capacity_l - self.collection_level_l)
        collected_l = min(collection_free_l, condensed_l)

        self.flask_level_l -= boil_off_l

        if boil_off_l > 1e-9 and self.flask_level_l > 1e-9:
            ethanol_bias = min(1.4, 0.6 + (self.flask_ethanol_frac * 2.8))
            ethanol_evap_frac = min(0.95, self.flask_ethanol_frac * ethanol_bias)
            ethanol_evap_l = boil_off_l * ethanol_evap_frac
            ethanol_remaining_l = max(0.0, self.flask_ethanol_frac * (self.flask_level_l + boil_off_l) - ethanol_evap_l)
            self.flask_ethanol_frac = min(0.95, ethanol_remaining_l / self.flask_level_l) if self.flask_level_l > 0 else 0.0

        if collected_l > 0:
            mix_alpha = min(1.0, collected_l / max(1.0, self.collection_level_l + collected_l))
            self.collection_temp_c = (1.0 - mix_alpha) * self.collection_temp_c + mix_alpha * (self.flask_temp_c - 12.0)
            self.collection_level_l += collected_l
        else:
            self.collection_temp_c += (self.cooling_inlet_temp_c - self.collection_temp_c) * (1.0 - math.exp(-dt_s / 1800.0))

        removed_heat_kw = self.vaporization_rate_lpm * 0.75 + max(0.0, self.flask_temp_c - 78.0) * 0.06
        flow_norm = max(0.05, self.cooling_flow_lpm / self.max_cooling_flow_lpm)
        delta_t = removed_heat_kw * (3.8 / flow_norm)
        self.cooling_outlet_temp_c = self.cooling_inlet_temp_c + delta_t


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, sim: PlantSimulator) -> None:
    peer = writer.get_extra_info("peername")
    try:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                writer.write(b'{"ok": false, "error": "invalid json"}\n')
                await writer.drain()
                continue

            cmd = message.get("cmd")
            if cmd == "set_controls":
                sim.set_controls(message.get("controls", {}))
                response = {"ok": True, "controls": asdict(sim.controls)}
            elif cmd == "get_state":
                response = {"ok": True, "state": asdict(sim.snapshot()), "controls": asdict(sim.controls)}
            elif cmd == "ping":
                response = {"ok": True, "msg": "pong"}
            else:
                response = {"ok": False, "error": f"unknown cmd: {cmd}"}

            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()
        if peer:
            print(f"client disconnected: {peer}")


async def run_simulation_loop(sim: PlantSimulator) -> None:
    dt_s = 0.5
    while True:
        sim.step(dt_s)
        await asyncio.sleep(dt_s)


async def main() -> None:
    sim = PlantSimulator()
    server = await asyncio.start_server(lambda r, w: handle_client(r, w, sim), HOST, PORT)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"Simulator listening on {addr}")

    sim_task = asyncio.create_task(run_simulation_loop(sim))
    async with server:
        await server.serve_forever()
    await sim_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Simulator stopped.")
