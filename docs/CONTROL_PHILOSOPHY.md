# Functional Design Specification: Control Philosophy & Interlocks
**Document ID:** SWaT-DOC-CP-001  
**Plant Area:** Stage 1 (Raw Water Storage) & Stage 2 (Chemical Pre-treatment)  
**Governing Code:** IEC 61131-3 (Structured Text) / ISA-84 (IEC 61511 Functional Safety)  
**Revision:** 1.0.0  

---

## 1. System Overview & Architectural Hierarchy

The SWaT control system executes real-time, deterministic control of fluid storage, transfer, and chemical treatment. The physical control logic resides entirely inside the containerized **OpenPLC Runtime v3**, running a periodic cyclic execution task.

```
+-------------------------------------------------------------------+
|               Supervisory / HMI Layer (UNS / SCADA)               |
|            Start/Stop Pushbuttons, Setpoints, E-Stop              |
+---------------------------------+---------------------------------+
                                  | Modbus/TCP (Port 502) / OPC UA (Port 4840)
+---------------------------------v---------------------------------+
|               OpenPLC Runtime v3 (task0: 100 ms Cycle)             |
|  - Safety Interlocks (HH Cutoffs, LL Permissive, E-Stop)          |
|  - Latching Circuits (P101, P102)                                 |
|  - Proportional Chemical Pacing (P201)                            |
+---------------------------------+---------------------------------+
                                  | Process Signals & Run Commands
+---------------------------------v---------------------------------+
|             SWaT Plant Model / Physical Equipment                 |
|  - Tanks: T101, T201                                              |
|  - Pumps: P101, P102, P201                                        |
|  - Sensors: LIT101, LIT201, FIT101, FIT201, AIT201               |
+-------------------------------------------------------------------+
```

### Execution Task Properties
- **Program Name:** `swat_control`
- **Cycle Time:** `T#100ms` (10 Hz scan rate)
- **Priority:** `0` (Deterministic Highest Priority)
- **Transpiler:** MatIEC &rarr; C &rarr; GCC native binary

---

## 2. Operating Modes

### 2.1 Manual Mode (Operator Pushbutton Control)
In Manual mode, operators trigger momentary start or stop pulses from SCADA, HMI, or testing scripts:
- **P101 Start Pulse (`%QX0.0`):** Initiates infeed pumping if all Stage 1 permissives are satisfied.
- **P101 Stop Pulse (`%QX0.1`):** Unlatches P101 run coil immediately.
- **P102 Start Pulse (`%QX0.2`):** Initiates water transfer to Stage 2 if suction tank `T101` has sufficient volume.
- **P102 Stop Pulse (`%QX0.3`):** Unlatches P102 run coil immediately.
*Safety interlocks (High-High cutoffs, Low-Low permissives, and E-Stop) strictly override manual commands at all times.*

### 2.2 Automated Chemical Pacing Mode (`%QX0.5`)
When `p201_auto_mode` is set to `TRUE` (default state):
- Chemical dosing pump `P201` is slaved to transfer pump `P102`.
- When `P102` is running (`%QX1.1 = TRUE`), `P201` automatically starts (`%QX1.2 = TRUE`) to maintain a steady concentration of chemical reagent in the transfer stream.
- When `P102` stops for any reason (operator stop, Low-Low trip, Stage 2 High-High cutoff, or E-Stop), `P201` trips **instantaneously** to prevent chemical over-dosing, line slugging, or hazardous pooling.

### 2.3 Hardware-In-the-Loop (HIL) Test Override Mode (`%QX0.6`)
To enable automated testing, commissioning, and deterministic test suites without sensor contention:
- Writing `TRUE` to Coil 6 (`test_override`) informs the simulator daemon (`swat_sim.py`) that synthetic test values are being injected into holding registers `%QW0`–`%QW4`.
- The simulator halts its physical ODE register writes and passively mirrors injected registers.
- Once Coil 6 is returned to `FALSE`, the simulator resumes normal physical mass-balance calculations.

### 2.4 Emergency Stop Mode (`%QX0.4`)
Asserting `emergency_stop` (`TRUE`):
- Forces all pump run commands (`P101`, `P102`, `P201`) to `FALSE` within a single PLC scan cycle (< 100 ms).
- Blocks all start permissives until `emergency_stop` is de-asserted and explicit operator restart pulses are issued.

---

## 3. Cause & Effect (C&E) Matrix / Interlock Table

| Safety Cause / Trip Event | Condition Threshold | Modbus Memory | P101 Action | P102 Action | P201 Action | Alarm Generated |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Master Emergency Stop** | `emergency_stop = TRUE` | `%QX0.4 = 1` | **TRIP** | **TRIP** | **TRIP** | System Tripped |
| **T101 High-High Level** | `lit101_raw_level >= 900 mm` | `%QW0 >= %QW5`| **TRIP** | Allowed | Allowed | `alarm_raw_hh` (`%QX1.3`) |
| **T101 Low-Low Level** | `lit101_raw_level <= 150 mm` | `%QW0 <= %QW6`| Allowed | **TRIP / INHIBIT**| **TRIP** | `alarm_raw_ll` (`%QX1.4`) |
| **T201 High-High Level** | `lit201_stage2_level >= 950 mm`| `%QW1 >= %QW7`| Allowed | **TRIP** | **TRIP** | `alarm_stage2_hh` (`%QX1.5`)|
| **P101 Stop Command** | `p101_stop_cmd = TRUE` | `%QX0.1 = 1` | **STOP** | No effect | No effect | - |
| **P102 Stop Command** | `p102_stop_cmd = TRUE` | `%QX0.3 = 1` | No effect | **STOP** | **STOP** | - |

---

## 4. Control Loop Specifications

### Loop 1: Infeed Raw Water Pump P101 Control & High-High Cutoff
- **Objective:** Control infeed supply to Raw Water Tank `T101` and protect vessel from overfilling/flooding.
- **Process Variable (PV):** `lit101_raw_level` (`%QW0`, 0–1000 mm).
- **Cutoff Limit Setpoint:** `raw_tank_hh_limit` (`%QW5`, default 900 mm).
- **Latching Circuit Logic:**
  ```pascal
  IF emergency_stop OR alarm_raw_hh OR p101_stop_cmd THEN
    p101_run_cmd := FALSE;
  ELSIF p101_start_cmd AND NOT alarm_raw_hh THEN
    p101_run_cmd := TRUE;
  END_IF;
  ```
- **Safety Response:** If `lit101_raw_level >= raw_tank_hh_limit`, `alarm_raw_hh` (`%QX1.3`) transitions to `TRUE`, dropping `p101_run_cmd` within 100 ms. Restarting is blocked as long as the alarm is active.

### Loop 2: Transfer Pump P102 Control & Low-Low Dry-Run Prevention
- **Objective:** Transfer water from `T101` to `T201` while preventing cavitation/impeller damage from dry suction, and preventing overfill of `T201`.
- **Suction Process Variable (PV1):** `lit101_raw_level` (`%QW0`, 0–1000 mm).
- **Discharge Process Variable (PV2):** `lit201_stage2_level` (`%QW1`, 0–1000 mm).
- **Permissive Threshold:** `raw_tank_ll_limit` (`%QW6`, default 150 mm).
- **Cutoff Threshold:** `stage2_tank_hh_limit` (`%QW7`, default 950 mm).
- **Latching Circuit Logic:**
  ```pascal
  IF emergency_stop OR alarm_raw_ll OR alarm_stage2_hh OR p102_stop_cmd THEN
    p102_run_cmd := FALSE;
  ELSIF p102_start_cmd AND NOT alarm_raw_ll AND NOT alarm_stage2_hh THEN
    p102_run_cmd := TRUE;
  END_IF;
  ```
- **Safety Response:** If suction level drops below 150 mm, `alarm_raw_ll` (`%QX1.4`) trips `P102`. Starting `P102` is inhibited until level exceeds 150 mm. If destination tank `T201` reaches 950 mm, `P102` is likewise tripped.

### Loop 3: Chemical Dosing Pump P201 Auto-Pacing
- **Objective:** Maintain chemical concentration by dosing proportionally during transfer.
- **Master Actuator:** `p102_run_cmd` (`%QX1.1`).
- **Slave Actuator:** `p201_run_cmd` (`%QX1.2`).
- **Logic:**
  ```pascal
  IF emergency_stop OR alarm_stage2_hh OR NOT p102_run_cmd THEN
    p201_run_cmd := FALSE;
  ELSIF p201_auto_mode AND p102_run_cmd THEN
    p201_run_cmd := TRUE;
  END_IF;
  ```
- **Safety Response:** Dosing is strictly locked to transfer flow. Zero transfer flow guarantees zero chemical injection.

---

## 5. Fail-Safe and Sanity Rules

1. **Setpoint Corruption Protection:**  
   If any setpoint holding register (`%QW5`–`%QW7`) is corrupted, initialized with `0`, or written with negative values, the PLC logic restores validated conservative defaults immediately:
   - `raw_tank_hh_limit := 900;`
   - `raw_tank_ll_limit := 150;`
   - `stage2_tank_hh_limit := 950;`
2. **De-energize to Trip Philosophy:**  
   All actuators (`p101_run_cmd`, `p102_run_cmd`, `p201_run_cmd`) are active-high. Loss of power, PLC crash, or bus disconnect drops all control signals to `0` (Safe Stopped State).
3. **Emergency Stop Precedence:**  
   The `emergency_stop` coil overrides all other logic and executes in the first rung of evaluation.
