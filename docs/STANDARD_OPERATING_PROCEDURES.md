# Standard Operating Procedures (SOP): SWaT Plant Operations
**Document ID:** SWaT-DOC-SOP-001  
**Plant Area:** Stage 1 (Raw Water Infeed) & Stage 2 (Pre-treatment & Dosing)  
**Applicability:** Plant Operators, OT Engineers, Commissioning Teams, AI Agents  
**Revision:** 1.0.0  

---

## 1. Document Purpose & Target Audience

This manual details the standard operating procedures (SOPs) for the safe operation, startup, monitoring, shutdown, and emergency recovery of the SWaT (Secure Water Treatment) simulation coupled with OpenPLC Runtime v3.

---

## 2. Table of Operating Procedures

| Procedure ID | Procedure Title | Purpose | Frequency |
| :--- | :--- | :--- | :--- |
| **SOP-001** | Cold Plant Inspection & Pre-Start | Verify infrastructure readiness and communication | Prior to system startup |
| **SOP-002** | Normal Plant Startup Sequence | Sequential startup of Stage 1 infeed and Stage 2 transfer | Operational start |
| **SOP-003** | Steady-State Process Monitoring | Continuous tracking of process variables and alarms | Routine continuous |
| **SOP-004** | Normal Plant Shutdown Sequence | Controlled, hazard-free shutdown of all pump circuits | Planned maintenance / end of run |
| **SOP-005** | Master Emergency Stop & Recovery | Immediate trip initiation and post-incident recovery | Emergency condition |
| **SOP-006** | High-High Level Alarm Response | Response to T101 or T201 vessel overfill alarms | Abnormal condition |
| **SOP-007** | Low-Low Level Alarm Response | Response to T101 depletion and dry-run pump trips | Abnormal condition |
| **SOP-008** | HIL Test Mode & Maintenance Override | Running deterministic verification suites without bus collision | Testing / Commissioning |

---

## SOP-001: Cold Plant Inspection & Pre-Start Checklist

### Objective
Ensure Docker container, OpenPLC Runtime, Modbus port, and simulation parameters are ready before starting equipment.

### Procedure Steps
1. **Verify Docker Container Health:**
   ```bash
   docker compose ps
   ```
   *Expected:* `openplc-runtime` container status is `Up` and healthy.
2. **Verify OpenPLC Web UI & Program Status:**
   - Open browser at `http://localhost:8080`.
   - Log in using administrative credentials (`openplc` / `openplc`).
   - Confirm hardware status indicates **"PLC Status: Running"**.
   - Verify active program is `swat_control`.
3. **Verify Port Accessibility:**
   - Confirm Modbus/TCP is accepting connections on `127.0.0.1:502`.
   - Confirm OPC UA is accessible on `127.0.0.1:4840`.
4. **Pre-Start State Verification:**
   - Emergency Stop (`%QX0.4`) must be `FALSE`.
   - Auto-Dosing Mode (`%QX0.5`) must be `TRUE`.
   - Initial Tank Levels (`%QW0`, `%QW1`) should read within nominal bounds (150 mm < Level < 900 mm).

---

## SOP-002: Normal Plant Startup Sequence

### Objective
Safely start continuous water infeed, transfer, and chemical pre-treatment in sequential stages.

### Procedure Steps
1. **Initiate Stage 1 Infeed Pumping:**
   - Verify `alarm_raw_hh` (`%QX1.3`) is `FALSE` (Tank 1 level < 900 mm).
   - Send a momentary pulse (150 ms) to `p101_start_cmd` (`%QX0.0 = TRUE` &rarr; `FALSE`).
   - Verify `p101_run_cmd` (`%QX1.0`) transitions to `TRUE`.
   - Monitor `FIT101` flow reading rises to ~150 L/min.
   - Observe `LIT101` tank level steadily rising.
2. **Verify Stage 2 Transfer Permissive:**
   - Verify `LIT101` level has exceeded the Low-Low permissive limit (> 150 mm).
   - Verify `alarm_raw_ll` (`%QX1.4`) is `FALSE`.
   - Verify Stage 2 tank `T201` is below High-High limit (< 950 mm).
3. **Initiate Stage 2 Transfer & Chemical Dosing:**
   - Send a momentary pulse (150 ms) to `p102_start_cmd` (`%QX0.2 = TRUE` &rarr; `FALSE`).
   - Verify `p102_run_cmd` (`%QX1.1`) transitions to `TRUE`.
   - Verify `p201_run_cmd` (`%QX1.2`) auto-starts in lockstep via auto-pacing.
   - Verify `FIT201` flow reading rises to ~120 L/min.
   - Verify `AIT201` chemical concentration stabilizes around 25.0 ppm.

---

## SOP-003: Steady-State Process Monitoring

### Objective
Maintain optimal water levels, flow dynamics, and chemical dosing during continuous operations.

### Nominal Parameter Band
| Parameter | Tag | Nominal Value | Safe Operating Band | Action if Outside Band |
| :--- | :--- | :--- | :--- | :--- |
| **Raw Water Tank Level** | `LIT101` | 500 – 750 mm | 200 – 850 mm | Cycle P101 to maintain buffer |
| **Stage 2 Tank Level** | `LIT201` | 300 – 700 mm | 150 – 900 mm | Balance P102 with downstream demand |
| **Raw Inflow Rate** | `FIT101` | 150 L/min | 140 – 160 L/min (P101 ON) | Check P101 strainer if flow drops |
| **Transfer Flow Rate** | `FIT201` | 120 L/min | 110 – 130 L/min (P102 ON) | Check P102 discharge line |
| **Chemical Concentration**| `AIT201` | 25.0 ppm | 20.0 – 30.0 ppm | Verify P201 dosing stroke / chemical stock |

---

## SOP-004: Normal Plant Shutdown Sequence

### Objective
Perform controlled, orderly cessation of fluid transfer and dosing.

### Procedure Steps
1. **Halt Transfer & Chemical Dosing (Stage 2):**
   - Send a momentary pulse (150 ms) to `p102_stop_cmd` (`%QX0.3 = TRUE` &rarr; `FALSE`).
   - Confirm `p102_run_cmd` (`%QX1.1`) drops to `FALSE`.
   - Confirm `p201_run_cmd` (`%QX1.2`) immediately unlatches and halts.
   - Confirm `FIT201` flow rate returns to 0 L/min.
2. **Halt Raw Water Infeed (Stage 1):**
   - Send a momentary pulse (150 ms) to `p101_stop_cmd` (`%QX0.1 = TRUE` &rarr; `FALSE`).
   - Confirm `p101_run_cmd` (`%QX1.0`) drops to `FALSE`.
   - Confirm `FIT101` flow rate returns to 0 L/min.
3. **Verify Safe Idle Condition:**
   - Confirm all pump status coils (`%QX1.0`, `%QX1.1`, `%QX1.2`) are `FALSE`.
   - Tank levels `T101` and `T201` remain stable.

---

## SOP-005: Master Emergency Stop (E-Stop) & Post-Trip Recovery

### Objective
Execute immediate shutdown during dangerous plant conditions and recover safely.

### 1. E-Stop Activation
- Write `TRUE` to `emergency_stop` (`%QX0.4 = TRUE`).
- **Immediate Outcome (< 100 ms):** OpenPLC forces `P101`, `P102`, and `P201` to `FALSE`. All start commands are disabled.

### 2. Post-Trip Investigation & Clearance
- Identify trip cause (mechanical fault, piping leak, severe instrument error).
- Once physical safety is confirmed, reset `emergency_stop` coil to `FALSE` (`%QX0.4 = FALSE`).
- *Note: Pumps will NOT restart automatically upon E-Stop release.*
- Re-prime the plant following **SOP-002 (Normal Plant Startup Sequence)**.

---

## SOP-006: High-High Level Cutoff (Alarm HH) Response

### Condition
`LIT101 >= 900 mm` trips `alarm_raw_hh` (`%QX1.3 = TRUE`).

### Automated Response
- OpenPLC automatically trips Infeed Pump `P101` (`%QX1.0 = FALSE`).
- Start commands for `P101` are inhibited.

### Operator Actions
1. Confirm `P101` has stopped and `FIT101` reads 0 L/min.
2. Run Transfer Pump `P102` (if downstream vessel `T201` has capacity) to draw down `T101`.
3. Once level drops below 900 mm, `alarm_raw_hh` automatically resets to `FALSE`.
4. Issue a start pulse on `p101_start_cmd` only after the level drops to nominal operating range (< 800 mm).

---

## SOP-007: Low-Low Level Permissive (Alarm LL) Response

### Condition
`LIT101 <= 150 mm` trips `alarm_raw_ll` (`%QX1.4 = TRUE`).

### Automated Response
- OpenPLC automatically trips Transfer Pump `P102` (`%QX1.1 = FALSE`) to prevent cavitation.
- Chemical Dosing Pump `P201` auto-stops in lockstep.
- Start commands for `P102` are inhibited.

### Operator Actions
1. Confirm `P102` and `P201` are stopped.
2. Start Infeed Pump `P101` (via `p101_start_cmd`) to replenish raw water in `T101`.
3. Once `LIT101` level rises above 150 mm, `alarm_raw_ll` automatically resets.
4. Restart `P102` following **SOP-002**.

---

## SOP-008: HIL Test Override & Verification Procedure

### Objective
Run automated test suites (`tests/test_ot_loop.py`) or AI diagnostic routines while the physics simulator (`swat_sim.py`) is running, without register bus collisions.

### Automated Test Procedure
1. Assert Coil 6 (`test_override = TRUE` on `%QX0.6`).
2. Simulator daemon detects Coil 6, pauses physical ODE register writing, and logs `[HIL:TEST_MODE]`.
3. Test suite injects synthetic test levels (e.g., 920 mm, 100 mm) and verifies PLC trip times.
4. Test suite concludes and clears Coil 6 (`test_override = FALSE` on `%QX0.6`).
5. Simulator resumes autonomous mass balance updates seamlessly.
