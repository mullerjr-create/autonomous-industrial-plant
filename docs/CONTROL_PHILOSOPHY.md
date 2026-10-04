# Functional Design Specification: Control Philosophy & Interlocks
**Document ID:** SWaT-DOC-CP-001  
**Plant Area:** Stage 1 (Raw Water Storage) & Stage 2 (Chemical Pre-treatment)  
**Governing Code:** IEC 61131-3 (Structured Text) / ISA-84 (IEC 61511 Functional Safety)  
**Revision:** 2.0.0 (Peer-Reviewed Critical Evaluation & Ground-Truth Alignment)  

---

## 1. System Overview & Critical Evaluation

This Functional Design Specification defines the operational logic, safety interlocks, and control invariants for the SWaT continuous process.

### Academic Invariants vs. Local OpenPLC Implementation

The physical control invariants published in the foundational SWaT cybersecurity and anomaly detection literature (Mathur & Tippenhauer 2016, Adepu & Mathur 2016, Goh et al. 2016) are compared side-by-side with our containerized OpenPLC logic below:

| Functional Goal | SUTD Published Literature Invariant | OpenPLC Emulation Invariant (`swat_control.st`) | Alignment Analysis |
| :--- | :--- | :--- | :--- |
| **Tank 1 Overfill Prevention** | $LIT101 \ge 800\text{ mm} \implies MV101\text{ Closes}$<br>$LIT101 \ge 1200\text{ mm} \implies \text{Emergency High-High Trip}$ | $lit101\_raw\_level \ge raw\_tank\_hh\_limit\ (900\text{ mm}) \implies p101\_run\_cmd\text{ TRIPS}$ | **Aligned:** Both systems enforce hard cutoff above high operating band. SUTD closes valve MV101; emulation trips infeed pump P101. |
| **Tank 1 Infeed Recovery** | $LIT101 \le 500\text{ mm} \implies MV101\text{ Opens}$ | Manual restart via $p101\_start\_cmd$ (or auto fill band) when $lit101\_raw\_level < 900\text{ mm}$. | **Adapted:** Emulation uses latching circuit with start permissive; SUTD uses hysteresis band on motorized valve. |
| **Transfer Pump Dry-Run Protection** | $LIT101 \le 250\text{ mm} \implies P101/P102\text{ TRIP \& INHIBIT}$ | $lit101\_raw\_level \le raw\_tank\_ll\_limit\ (150\text{ mm}) \implies p102\_run\_cmd\text{ TRIPS \& INHIBIT}$ | **Aligned:** Prevents pump impeller destruction and cavitation when suction head is depleted. |
| **Destination Tank Overfill Protection** | $LIT301 \ge 1000\text{ mm} \implies P101/P102\text{ TRIP}$ | $lit201\_stage2\_level \ge stage2\_tank\_hh\_limit\ (950\text{ mm}) \implies p102\_run\_cmd\text{ TRIPS}$ | **Aligned:** Both protect the downstream vessel from overflow by tripping upstream transfer pumping. |
| **Chemical Dosing Pacing** | $P101/P102\text{ RUN} \iff P201\text{--}P206\text{ RUN}$<br>$P101/P102\text{ STOP} \implies P201\text{--}P206\text{ STOP}$ | $p102\_run\_cmd\text{ RUN} \iff p201\_run\_cmd\text{ RUN}$<br>$p102\_run\_cmd\text{ STOP} \implies p201\_run\_cmd\text{ STOP}$ | **Identical:** Strictly prevents chemical slugging or hazardous concentration spikes in the transfer stream. |

---

## 2. Control System Execution Architecture

The control logic executes deterministically inside **OpenPLC Runtime v3** inside Docker:

```
+-------------------------------------------------------------------+
|               Supervisory / HMI Layer (UNS / SCADA)               |
|            Start/Stop Pushbuttons, Setpoints, E-Stop              |
+---------------------------------+---------------------------------+
                                  | Modbus/TCP (Port 502) / OPC UA (Port 4840)
+---------------------------------v---------------------------------+
|               OpenPLC Runtime v3 (task0: 100 ms Cycle)             |
|  - Rung 1: Safety Interlocks (HH Cutoffs, LL Permissive, E-Stop)  |
|  - Rung 2: Infeed Latching Circuit (P101)                         |
|  - Rung 3: Transfer Latching Circuit (P102)                       |
|  - Rung 4: Proportional Chemical Pacing (P201)                    |
+---------------------------------+---------------------------------+
                                  | Process Signals & Run Commands
+---------------------------------v---------------------------------+
|             SWaT Plant Model / Physical Equipment                 |
|  - Tanks: T101, T201                                              |
|  - Pumps: P101, P102, P201                                        |
|  - Sensors: LIT101, LIT201, FIT101, FIT201, AIT201               |
+-------------------------------------------------------------------+
```

### Execution Parameters
- **Task Identifier:** `task0`
- **Cycle Period:** `T#100ms` (10 Hz fixed scan interval)
- **Task Priority:** `0` (Deterministic Highest Priority)
- **Modbus Slave Address:** Unit ID `1`

---

## 3. Operating Modes

### 3.1 Manual Mode (Operator Pushbutton Control)
- **P101 Start Pulse (`%QX0.0`):** Latches infeed pump `P101` ON if `alarm_raw_hh` is `FALSE`.
- **P101 Stop Pulse (`%QX0.1`):** Unlatches `P101` immediately.
- **P102 Start Pulse (`%QX0.2`):** Latches transfer pump `P102` ON if `alarm_raw_ll` is `FALSE` and destination tank `alarm_stage2_hh` is `FALSE`.
- **P102 Stop Pulse (`%QX0.3`):** Unlatches `P102` immediately.

### 3.2 Automated Chemical Pacing Mode (`%QX0.5`)
When `p201_auto_mode` is enabled (`TRUE` by default):
- Dosing pump `P201` is strictly slaved to transfer pump `P102`.
- `p102_run_cmd = TRUE` &rarr; `p201_run_cmd = TRUE`.
- Any trip or stop of `P102` instantly trips `P201` within the same 100 ms scan cycle.

### 3.3 Hardware-In-the-Loop (HIL) Test Override Mode (`%QX0.6`)
- Asserting Coil 6 (`test_override = TRUE`) decouples the real-time physics ODE writes in `swat_sim.py`.
- Allows test suites and AI diagnostic routines to inject synthetic test levels (e.g., 920 mm, 100 mm) into holding registers without bus collisions.
- Clearing Coil 6 (`test_override = FALSE`) returns the plant to autonomous physical simulation.

### 3.4 Master Emergency Stop (`%QX0.4`)
- Asserting `emergency_stop = TRUE` drops all pumps (`P101`, `P102`, `P201`) to `FALSE` in scan cycle 0.
- All start permissives remain locked out until the E-Stop is de-asserted and explicit operator restart pulses are issued.

---

## 4. Cause & Effect (C&E) Matrix / Interlock Table

| Safety Cause / Event | Condition Threshold | Modbus Memory | P101 Action | P102 Action | P201 Action | Safety Alarm |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Master Emergency Stop** | `emergency_stop = TRUE` | `%QX0.4 = 1` | **TRIP** | **TRIP** | **TRIP** | - |
| **T101 High-High Overflow**| `lit101_raw_level >= 900 mm` | `%QW0 >= %QW5`| **TRIP** | Permitted | Permitted | `alarm_raw_hh` (`%QX1.3`) |
| **T101 Low-Low Dry-Run** | `lit101_raw_level <= 150 mm` | `%QW0 <= %QW6`| Permitted | **TRIP / INHIBIT**| **TRIP** | `alarm_raw_ll` (`%QX1.4`) |
| **Stage 2 High-High Overflow**| `lit201_stage2_level >= 950 mm`| `%QW1 >= %QW7`| Permitted | **TRIP** | **TRIP** | `alarm_stage2_hh` (`%QX1.5`)|
| **P101 Stop Command** | `p101_stop_cmd = TRUE` | `%QX0.1 = 1` | **STOP** | No effect | No effect | - |
| **P102 Stop Command** | `p102_stop_cmd = TRUE` | `%QX0.3 = 1` | No effect | **STOP** | **STOP** | - |

---

## 5. Structured Text Implementation Logic (`swat_control.st`)

```pascal
(* 1. Safety Interlocks & Alarms Evaluation *)
IF lit101_raw_level >= raw_tank_hh_limit THEN
  alarm_raw_hh := TRUE;
ELSE
  alarm_raw_hh := FALSE;
END_IF;

IF lit101_raw_level <= raw_tank_ll_limit THEN
  alarm_raw_ll := TRUE;
ELSE
  alarm_raw_ll := FALSE;
END_IF;

IF lit201_stage2_level >= stage2_tank_hh_limit THEN
  alarm_stage2_hh := TRUE;
ELSE
  alarm_stage2_hh := FALSE;
END_IF;

(* 2. Infeed Raw Water Pump P101 Latching Circuit *)
IF emergency_stop OR alarm_raw_hh OR p101_stop_cmd THEN
  p101_run_cmd := FALSE;
ELSIF p101_start_cmd AND NOT alarm_raw_hh THEN
  p101_run_cmd := TRUE;
END_IF;

(* 3. Transfer Pump P102 Latching Circuit *)
IF emergency_stop OR alarm_raw_ll OR alarm_stage2_hh OR p102_stop_cmd THEN
  p102_run_cmd := FALSE;
ELSIF p102_start_cmd AND NOT alarm_raw_ll AND NOT alarm_stage2_hh THEN
  p102_run_cmd := TRUE;
END_IF;

(* 4. Chemical Dosing Pump P201 Auto-Pacing *)
IF emergency_stop OR alarm_stage2_hh OR NOT p102_run_cmd THEN
  p201_run_cmd := FALSE;
ELSIF p201_auto_mode AND p102_run_cmd THEN
  p201_run_cmd := TRUE;
END_IF;
```

---

## 6. Fail-Safe and Sanity Rules

1. **Setpoint Corruption Recovery:**  
   If any setpoint holding register (`%QW5`–`%QW7`) is corrupted or set to $\le 0$, the controller reverts automatically to validated safety setpoints:
   - `raw_tank_hh_limit := 900;`
   - `raw_tank_ll_limit := 150;`
   - `stage2_tank_hh_limit := 950;`
2. **De-energize to Trip Philosophy:**  
   Actuator coils are active-high. Loss of power or communication drops outputs to `0` (Safe Stopped State).
3. **Emergency Stop Precedence:**  
   The `emergency_stop` condition is evaluated in every rung, guaranteeing immediate actuator cessation.
