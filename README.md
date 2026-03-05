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

## Feedback equations by component

The simulator runs at fixed step `dt_s = 0.5 s` and applies these equations each step.

### 1) Cooling-water source (ambient + diurnal feedback)

- Day phase:
  - `phase_day = (time_now mod 86400) / 86400`
- Diurnal term:
  - `diurnal = 2.3 * sin(2π * (phase_day - 0.25))`
- Slow stochastic day offset:
  - `offset <- clamp(offset + U(-0.02, 0.02) * (dt_s/60), -1.5, 1.5)`
- Inlet target and first-order lag:
  - `T_cool_in_target = 25.0 + diurnal + offset`
  - `alpha_cool = 1 - exp(-dt_s/420)`
  - `T_cool_in <- T_cool_in + (T_cool_in_target - T_cool_in) * alpha_cool`

### 2) Level control loop (operator setpoint -> feed path)

- Error:
  - `e_level = L_flask_sp - L_flask`
- PID output:
  - `u_level = Kp*e + Ki*∫e dt + Kd*(de/dt)`
  - with `Kp=0.028`, `Ki=0.0035`, `Kd=0.01`
  - integral clamped to `[-400, 400]`
- Manipulated variables:
  - `demand = clamp01(u_level)`
  - `feed_valve = demand`
  - `feed_pump_speed = 0.2 + 0.8*demand`

### 3) Temperature control loop (operator setpoint -> heater/cooling)

- Error:
  - `e_temp = T_flask_sp - T_flask`
- Heater PID:
  - `u_heat = Kp*e + Ki*∫e dt + Kd*(de/dt)`
  - with `Kp=0.045`, `Ki=0.0035`, `Kd=0.008`
  - `heating_power = clamp01(u_heat)`
- Cooling assist (bias when over setpoint):
  - `cooling_bias = max(0, T_flask - T_flask_sp)`
  - `cooling_pump_speed = clamp01(0.12 + 0.88*(cooling_bias/12.0))`

### 4) Feedstock tank -> flask mass balance

- Feed flow command:
  - `Q_feed = Q_feed_max * feed_valve * feed_pump_speed`
  - `Q_feed_max = 18 L/min`
- Transfer in one step:
  - `V_feed = min(L_feedstock, Q_feed * dt_min, free_volume_flask)`
  - where `dt_min = dt_s / 60`
- Level updates:
  - `L_feedstock <- L_feedstock - V_feed`
  - `L_flask <- L_flask + V_feed`
- Flask composition mixing:
  - `xE_flask <- (L_flask_old*xE_flask_old + V_feed*xE_feed) / (L_flask_old + V_feed)`

### 5) Flask thermal model + boil-up feedback

- Cooling flow from pump:
  - `Q_cool = Q_cool_max * cooling_pump_speed`, `Q_cool_max = 55 L/min`
- Effective thermal drive:
  - `heating_term = 3.9 * heating_power`
  - `cooling_term = 1.7 * cooling_pump_speed + max(0, T_cool_in - 25)*0.08`
  - `T_target = 26 + 80*max(0, heating_term - cooling_term)`
- First-order thermal response:
  - `alpha_T = 1 - exp(-dt_s/200)`
  - `T_flask <- T_flask + (T_target - T_flask)*alpha_T`
- Vaporization rate:
  - `temp_drive = max(0, T_flask - 78)/18`
  - `ethanol_boost = 0.25 + xE_flask`
  - `Q_vap = min(Q_vap_max, heating_power*temp_drive*ethanol_boost*Q_vap_max)`
  - `Q_vap_max = 5 L/min`

### 6) Column/condenser and collection feedback

- Boil-off and condenser efficiency:
  - `V_boil = min(L_flask, Q_vap*dt_min)`
  - `eta_cond = clamp(0.18 + 0.8*cooling_pump_speed - max(0, T_cool_in - 25)*0.015, 0.05, 0.98)`
  - `V_condensed = V_boil * eta_cond`
- Collection intake (capacity-limited):
  - `V_collect = min(free_collection_volume, V_condensed)`
- Flask level decrease:
  - `L_flask <- L_flask - V_boil`
- Ethanol enrichment/depletion in flask during boil-off:
  - `ethanol_bias = min(1.4, 0.6 + 2.8*xE_flask)`
  - `xE_evap = min(0.95, xE_flask*ethanol_bias)`
  - remaining ethanol used to recompute `xE_flask`
- Collection temperature blending:
  - if collecting: weighted mix toward `(T_flask - 12)`
  - if not collecting: relax toward `T_cool_in` with `tau = 1800 s`

### 7) Cooling outlet temperature feedback

- Removed heat estimate:
  - `Q_removed = 0.75*Q_vap + 0.06*max(0, T_flask - 78)`
- Flow normalization:
  - `flow_norm = max(0.05, Q_cool / Q_cool_max)`
- Outlet temperature rise:
  - `ΔT_cool = Q_removed * (3.8 / flow_norm)`
  - `T_cool_out = T_cool_in + ΔT_cool`

### 8) Sensor back-calculation

- Specific gravity estimate from ethanol fraction:
  - `SG_flask = (1 - xE_flask)*1.000 + xE_flask*0.789`

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
