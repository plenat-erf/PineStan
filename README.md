# PineStan Distillation HMI + Simulator

This repository now contains two Python programs:

- `simulator.py`: A process simulation for a small ethanol/water distillation system.
- `hmi.py`: A terminal user interface (TUI) that acts as the HMI and controls the simulator.

## Process modeled

Primary process:

`feedstock tank -> valve -> feed pump -> distillation flask -> distillation column -> collection tank`

Cooling process:

`water intake -> cooling pump -> column cooling sleeve -> waste outlet`

Sensors exposed by the simulator include:

- Feedstock tank level
- Feed line flow rate
- Distillation flask temperature
- Distillation flask specific gravity (implied ethanol/water ratio)
- Cooling inlet/outlet temperatures
- Cooling water flow rate
- Collection tank level
- Collection tank temperature

## Run

```bash
python3 simulator.py
```

In another terminal:

```bash
python3 hmi.py
```

## HMI controls

- Arrow up/down: select control
- Arrow left/right: adjust selected control
- `Q`: quit

Controls currently available:

- Feed valve position
- Feed pump speed
- Heater power
- Cooling pump speed

The simulator is dynamic, with interconnected variables so operator changes in the HMI influence temperatures, flows, levels, and composition over time.
