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

The operator sets high-level setpoints:

- **Flask temperature setpoint** (°C)
- **Flask level setpoint** (L)

Internal PID loops in the simulator automatically manipulate:

- Feed valve position
- Feed pump speed
- Heater power
- Cooling pump speed

These manipulated variables are fed back to the GUI as live actuator readings.

## GUI visuals (Siemens-inspired)

The GUI renders a darker industrial SCADA canvas with simplified PFD symbols:

- Tanks with live infill levels
- Valve open/closed symbol
- Pump tachometer indicators
- Thermometer bars
- Distillation column drawn with a central distillate path and side cooling-jacket paths
- Cooling lines split to each side of the column jacket and rejoin at the outlet
- Animated dashed flow in each process stream, with dash speed proportional to that stream's actual flow rate
- Maximized startup window for full-screen operator use

## Run

Start simulator:

```bash
python3 simulator.py
```

Start GUI HMI in another terminal:

```bash
python3 hmi.py
```
