# PineStan Distillation HMI + Simulator

This repository contains two Python programs:

- `simulator.py`: Dynamic process simulation for a small ethanol/water distillation system.
- `hmi.py`: GUI SCADA-style HMI built with Tkinter.

## Process modeled

Primary process line:

`feedstock tank -> valve -> feed pump -> distillation flask -> distillation column -> collection tank`

Cooling process line:

`water intake -> cooling pump -> column cooling sleeve -> waste outlet`

## Control structure

The operator now sets only high-level setpoints:

- **Flask temperature setpoint** (°C)
- **Flask level setpoint** (L)

The simulator uses internal PID loops to automatically drive:

- Feed valve position
- Feed pump speed
- Heater power
- Cooling pump speed

These manipulated variables are fed back to the GUI as live actuator values.

## GUI visuals

The GUI displays SCADA symbols and live dynamics:

- Tanks with level infill
- Valve open/closed state symbol
- Pump tachometers
- Thermometer graphics
- Animated dashed flow in pipes, with animation speed proportional to actual flow rate
- Maximized startup window for full-screen operator view

## Run

Start simulator:

```bash
python3 simulator.py
```

Start GUI HMI in another terminal:

```bash
python3 hmi.py
```
