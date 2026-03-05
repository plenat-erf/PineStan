# PineStan Distillation HMI + Simulator

This repository contains two Python programs:

- `simulator.py`: A dynamic process simulation for a small ethanol/water distillation system.
- `hmi.py`: A GUI SCADA-style HMI built with Tkinter.

## Process modeled

Primary process line:

`feedstock tank -> valve -> feed pump -> distillation flask -> distillation column -> collection tank`

Cooling process line:

`water intake -> cooling pump -> column cooling sleeve -> waste outlet`

## Simulator signals

The simulator exposes these live values to the HMI:

- Feedstock tank level
- Feed line flow rate
- Distillation flask level + temperature
- Distillation flask specific gravity and ethanol fraction
- Vaporization rate from flask to column
- Cooling inlet/outlet temperatures and flow
- Collection tank level + temperature

## GUI HMI visuals

The GUI displays simple SCADA symbols:

- **Tanks** with level infill (% full)
- **Animated dashed pipe lines** where dash speed changes with process flow
- **Valve symbol** that indicates open/closed state from valve position
- **Pump tachometers** for feed and cooling pump speeds
- **Thermometer graphics** for flask, cooling inlet/outlet, and collection temperatures

## Run

Start the simulator:

```bash
python3 simulator.py
```

Start the GUI HMI in another terminal:

```bash
python3 hmi.py
```

## Controls

Use the right-side sliders in the GUI:

- Feed valve position
- Feed pump speed
- Heater power
- Cooling pump speed

All controls write back to the simulator and immediately influence flows, levels, and temperatures.
