# Autonomous Industrial Plant: Phase 0 & Phase 1 OT Foundation

A local, OEM-agnostic Industrial DataOps and AI reference architecture decoupled into deterministic OT control (OpenPLC Runtime v3 + SWaT physics simulation) and higher-level contextual layers.

This repository implements **Phase 0 (Workspace & Docker Setup)** and **Phase 1 (OT Foundation & Simulation)** of the Master Implementation Roadmap.

---

## 1. Architecture Overview (Phase 0 & Phase 1)

```
+-------------------------------------------------------------------------+
|                  OT LAYER: Simulation & Deterministic Control           |
|                                                                         |
|   +--------------------------+           +--------------------------+   |
|   |   SWaT Plant Simulator   |  Modbus   |   OpenPLC Runtime v3     |   |
|   |    (Python ODE Loop)     |<--------->|  (IEC 61131-3 ST Engine) |   |
|   |                          |  TCP 502  |                          |   |
|   |   - Raw Pump P101        |           |   - Start/Stop Latching  |   |
|   |   - Storage Tank T101    |           |   - High-High Cutoff     |   |
|   |   - Transfer Pump P102   |           |   - Low-Low Dry Run Trip |   |
|   |   - Dosing Pump P201     |           |   - Dosing Auto Pacing   |   |
|   |   - Tank T201 (Stage 2)  |           |                          |   |
|   +--------------------------+           +--------------------------+   |
|                 ^                                      ^                |
|                 |                                      |                |
+-----------------|--------------------------------------|----------------+
                  |                                      |
                  |                                Port 8080 (Web UI)
                  |                                Port 4840 (OPC UA)
        +-------------------+
        | Deterministic Test|
        |  test_ot_loop.py  |
        +-------------------+
```

---

## 2. Directory Structure

```
autonomous-industrial-plant/
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git ignore rules for Python, venv, and PLC artifacts
├── docker-compose.yml               # Docker Compose defining industrial-network & OpenPLC
├── requirements.txt                 # Pinned dependencies for Python environment
├── swat_control.st                  # Root copy of IEC 61131-3 Structured Text logic
├── README.md                        # Phase 0 & Phase 1 documentation
├── docker/
│   └── openplc/
│       └── Dockerfile               # Container build recipe for OpenPLC Runtime v3
├── plc/
│   └── swat_control.st              # IEC 61131-3 control logic source file
├── simulator/
│   ├── __init__.py
│   └── swat_sim.py                  # SWaT first-principles ODE simulation loop
├── config/                          # Scaffolding for configuration files
├── docs/                            # Reference engineering documentation
│   ├── PID_SPECIFICATION.md         # Piping & Instrumentation Diagram & ISA-5.1 index
│   ├── CONTROL_PHILOSOPHY.md        # Functional Design Specification & C&E Matrix
│   └── STANDARD_OPERATING_PROCEDURES.md # SOP manual for startup, shutdown & alarms
└── tests/
    ├── __init__.py
    └── test_ot_loop.py              # Deterministic OT smoke & interlock test suite
```

---

## 3. Industrial Modbus/TCP Address Mapping

### Discrete Outputs / Coils (`%QX`) - Function Codes 01, 05, 15

| Address | IEC Symbol | Tag Name | Type | Description |
|---|---|---|---|---|
| **0** | `%QX0.0` | `p101_start_cmd` | Input (Cmd) | Raw Water Infeed Pump P101 Start Pushbutton |
| **1** | `%QX0.1` | `p101_stop_cmd` | Input (Cmd) | Raw Water Infeed Pump P101 Stop Pushbutton |
| **2** | `%QX0.2` | `p102_start_cmd` | Input (Cmd) | Transfer Pump P102 Start Pushbutton |
| **3** | `%QX0.3` | `p102_stop_cmd` | Input (Cmd) | Transfer Pump P102 Stop Pushbutton |
| **4** | `%QX0.4` | `emergency_stop` | Input (Cmd) | Emergency Stop Pushbutton (Trips all pumps) |
| **5** | `%QX0.5` | `p201_auto_mode` | Input (Cmd) | Chemical Dosing Pump P201 Auto Pacing Enable |
| **8** | `%QX1.0` | `p101_run_cmd` | Output (Actuator) | Raw Water Infeed Pump P101 Run Status |
| **9** | `%QX1.1` | `p102_run_cmd` | Output (Actuator) | Transfer Pump P102 Run Status |
| **10** | `%QX1.2` | `p201_run_cmd` | Output (Actuator) | Chemical Dosing Pump P201 Run Status |
| **11** | `%QX1.3` | `alarm_raw_hh` | Output (Alarm) | Tank T101 High-High Level Cutoff Active |
| **12** | `%QX1.4` | `alarm_raw_ll` | Output (Alarm) | Tank T101 Low-Low Permissive Trip Active |
| **13** | `%QX1.5` | `alarm_stage2_hh`| Output (Alarm) | Stage 2 Tank T201 High-High Cutoff Active |

### Holding Registers (`%QW`) - Function Codes 03, 06, 16

| Address | IEC Symbol | Tag Name | Eng. Unit | Range | Description |
|---|---|---|---|---|---|
| **0** | `%QW0` | `lit101_raw_level` | mm | 0 - 1000 | Raw Water Tank T101 Level Transmitter |
| **1** | `%QW1` | `lit201_stage2_level`| mm | 0 - 1000 | Stage 2 Dosing Tank T201 Level Transmitter |
| **2** | `%QW2` | `fit101_raw_flow` | L/min | 0 - 300 | Raw Infeed Flow Transmitter FIT101 |
| **3** | `%QW3` | `fit201_transfer_flow`| L/min | 0 - 300 | Transfer Flow Transmitter FIT201 |
| **4** | `%QW4` | `ait201_chemical_ppm`| ppm | 0 - 100 | Chemical Concentration Transmitter AIT201 |
| **5** | `%QW5` | `raw_tank_hh_limit` | mm | 500 - 1000| High-High Level Cutoff Setpoint (Default: 900) |
| **6** | `%QW6` | `raw_tank_ll_limit` | mm | 0 - 400 | Low-Low Permissive Setpoint (Default: 150) |
| **7** | `%QW7` | `stage2_tank_hh_limit`| mm | 500 - 1000| Stage 2 High-High Cutoff Setpoint (Default: 950)|

---

## 4. Engineering Reference Documentation

For detailed functional specifications, piping layouts, and operational procedures:

- **[Piping & Instrumentation Diagram (P&ID) Specification](docs/PID_SPECIFICATION.md):** Full ANSI/ISA-5.1 schematic, equipment schedule (T101, T201, P101, P102, P201), instrument index, and piping schedule.
- **[Control Philosophy & Functional Design Specification](docs/CONTROL_PHILOSOPHY.md):** Detailed IEC 61131-3 logic architecture, operating modes, Cause & Effect (C&E) Matrix, safety interlocks, and fail-safe behaviors.
- **[Standard Operating Procedures (SOP)](docs/STANDARD_OPERATING_PROCEDURES.md):** Formal operational procedures (SOP-001 through SOP-008) for inspection, cold start, steady-state monitoring, shutdown, E-Stop recovery, and HIL testing.

---

## 5. Step-by-Step Execution Guide

### Step 1: Environment Setup
Initialize the virtual environment and install pinned dependencies:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Step 2: Launch OpenPLC Runtime v3 in Docker
Ensure Docker Desktop is running, then launch the service:

```powershell
docker compose up -d
```

Verify that the container is healthy:
```powershell
docker compose ps
docker compose logs -f openplc
```

Exposed service ports:
- **`502`**: Modbus/TCP Fieldbus Port
- **`4840`**: Embedded OPC UA Server
- **`8080`**: OpenPLC Web Management UI

---

### Step 3: Upload IEC 61131-3 Logic to OpenPLC Web UI

1. Open your browser and navigate to:
   ```
   http://localhost:8080
   ```
2. Log in with the default OpenPLC credentials:
   - **Username:** `openplc`
   - **Password:** `openplc`
3. In the left navigation menu, click **Programs**.
4. In the **Add new program** section:
   - Click **Choose File** and select `swat_control.st` (located in the repository root or `plc/swat_control.st`).
   - Enter Program Name: `swat_control`
   - Description: `SWaT Continuous Water Treatment Plant Control Logic`
   - Click **Upload Program**.
5. Once uploaded, OpenPLC will compile the Structured Text file via MatIEC.
6. When compilation completes successfully, click **Go to Dashboard**.
7. In the Dashboard, click **Start PLC**.
8. Verify that the dashboard status indicator changes to **Running**.

---

### Step 4: Run the SWaT Process Simulator

Launch the Python physics simulation daemon:

```powershell
.venv\Scripts\python simulator/swat_sim.py
```

The simulator connects to OpenPLC on `127.0.0.1:502`, reads pump run outputs (`%QX1.0` - `%QX1.2`), integrates fluid mass balances ($dV/dt = Q_{in} - Q_{out}$), and writes process transmitter values to holding registers (`%QW0` - `%QW4`) at 10 Hz (100 ms loop).

**Standalone Physics Test (Offline Mode):**
To run the physics simulation without connecting to OpenPLC:
```powershell
.venv\Scripts\python simulator/swat_sim.py --standalone
```

---

### Step 5: Execute Deterministic OT Smoke Tests

In a separate terminal window, run the automated test suite to verify dynamic register updates and safety interlocks:

```powershell
# Using the built-in test runner
.venv\Scripts\python tests/test_ot_loop.py

# Or using pytest
.venv\Scripts\pytest tests/test_ot_loop.py -v
```

The test validates:
1. Bidirectional register read/write integrity over Modbus/TCP.
2. Pushbutton start/stop latching on Raw Water Pump P101.
3. High-High tank cutoff interlock: injects level $\ge 900\text{ mm}$ and asserts immediate pump trip within one scan cycle.
4. Low-Low dry-run permissive: injects level $\le 150\text{ mm}$ and asserts Transfer Pump P102 start inhibition.
5. Chemical dosing auto-pacing with transfer flow.

