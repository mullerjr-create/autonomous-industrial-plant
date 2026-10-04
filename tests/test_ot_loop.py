#!/usr/bin/env python3
"""
Deterministic OT Loop & Safety Interlock Verification Test
===========================================================

Verifies end-to-end Modbus/TCP synchronization between the client, OpenPLC Runtime v3,
and the physical control logic defined in `plc/swat_control.st`.

Test Matrix:
------------
1. Connection & Register Access:
   - Connects to OpenPLC over Modbus/TCP (Port 502).
   - Writes and verifies analog process values in Holding Registers (%QW0-%QW4).

2. Pump Start/Stop Latching Logic:
   - Pulses P101 Start Pushbutton (Coil 0).
   - Asserts P101 Run Output (Coil 8) latches to TRUE.
   - Pulses P101 Stop Pushbutton (Coil 1).
   - Asserts P101 Run Output (Coil 8) resets to FALSE.

3. High-High Level Cutoff Interlock (Raw Water Tank T101):
   - Starts P101 in safe operating band (Level = 500 mm).
   - Injects high tank level (Level = 920 mm >= 900 mm HH limit) into %QW0.
   - Asserts Alarm HH (Coil 11) transitions to TRUE.
   - Asserts P101 Run Output (Coil 8) trips to FALSE immediately.
   - Attempts restart during high level; asserts start is strictly inhibited.

4. Low-Low Level Permissive Dry-Run Interlock (Transfer Pump P102):
   - Injects low tank level (Level = 100 mm <= 150 mm LL limit) into %QW0.
   - Asserts Alarm LL (Coil 12) transitions to TRUE.
   - Pulses P102 Start Pushbutton (Coil 2).
   - Asserts P102 Run Output (Coil 9) remains FALSE (dry-run prevention permissive).
   - Restores safe level (500 mm) and verifies P102 can then start normally.

5. Chemical Dosing Pump P201 Automation Pacing:
   - Verifies P201 (Coil 10) paces automatically with Transfer Pump P102 (Coil 9).
   - Verifies P201 halts immediately when Transfer Pump stops.
"""

import os
import sys
import time
import pytest

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    ModbusTcpClient = None

# Default test environment configuration
OPENPLC_HOST = os.getenv("OPENPLC_HOST", "127.0.0.1")
OPENPLC_PORT = int(os.getenv("OPENPLC_MODBUS_PORT", "502"))
SLAVE_ID = 1

# Modbus Address Mapping Definitions
COIL_P101_START = 0       # %QX0.0
COIL_P101_STOP = 1        # %QX0.1
COIL_P102_START = 2       # %QX0.2
COIL_P102_STOP = 3        # %QX0.3
COIL_EMERGENCY_STOP = 4   # %QX0.4
COIL_P201_AUTO = 5        # %QX0.5
COIL_TEST_OVERRIDE = 6    # %QX0.6 (HIL Test Override: signals simulator to pause register writes)

COIL_P101_RUN = 8         # %QX1.0
COIL_P102_RUN = 9         # %QX1.1
COIL_P201_RUN = 10        # %QX1.2
COIL_ALARM_RAW_HH = 11    # %QX1.3
COIL_ALARM_RAW_LL = 12    # %QX1.4
COIL_ALARM_S2_HH = 13     # %QX1.5

REG_LIT101_LEVEL = 0      # %QW0 (mm)
REG_LIT201_LEVEL = 1      # %QW1 (mm)
REG_FIT101_FLOW = 2       # %QW2 (L/min)
REG_FIT201_FLOW = 3       # %QW3 (L/min)
REG_AIT201_CHEM = 4       # %QW4 (ppm)
REG_LIMIT_RAW_HH = 5      # %QW5 (mm setpoint)
REG_LIMIT_RAW_LL = 6      # %QW6 (mm setpoint)


def _call_compat(func, *args, **kwargs):
    """Handles pymodbus version variance between device_id=, slave=, and unit= kwargs."""
    for kw in ("device_id", "slave", "unit"):
        try:
            return func(*args, **{kw: SLAVE_ID}, **kwargs)
        except TypeError:
            continue
    return func(*args, **kwargs)


def pulse_coil(client, coil_address: int, pulse_sec: float = 0.15):
    """Simulates a momentary push button press on an industrial control panel."""
    _call_compat(client.write_coil, address=coil_address, value=True)
    time.sleep(pulse_sec)
    _call_compat(client.write_coil, address=coil_address, value=False)
    time.sleep(0.05)


def read_coil(client, coil_address: int) -> bool:
    """Reads a single coil state."""
    rr = _call_compat(client.read_coils, address=coil_address, count=1)
    assert rr is not None and not rr.isError(), f"Failed to read coil {coil_address}: {rr}"
    return bool(rr.bits[0])


def write_holding_reg(client, address: int, value: int):
    """Writes a 16-bit integer to a holding register."""
    rq = _call_compat(client.write_register, address=address, value=value)
    assert rq is not None and not rq.isError(), f"Failed to write register {address}: {rq}"


def read_holding_reg(client, address: int) -> int:
    """Reads a single holding register."""
    rr = _call_compat(client.read_holding_registers, address=address, count=1)
    assert rr is not None and not rr.isError(), f"Failed to read register {address}: {rr}"
    return int(rr.registers[0])


@pytest.fixture(scope="module")
def modbus_client():
    """Pytest fixture providing a connected ModbusTcpClient or skipping if PLC is offline."""
    if ModbusTcpClient is None:
        pytest.fail("pymodbus is not installed in the environment. Run pip install -r requirements.txt")

    client = ModbusTcpClient(OPENPLC_HOST, port=OPENPLC_PORT, timeout=2.0)
    connected = client.connect()
    if not connected:
        pytest.skip(
            f"OpenPLC Runtime is not reachable at {OPENPLC_HOST}:{OPENPLC_PORT}. "
            f"Ensure Docker is running ('docker compose up -d') and swat_control.st is compiled."
        )

    # Enable HIL test override mode so simulator does not collide on register writes
    _call_compat(client.write_coil, address=COIL_TEST_OVERRIDE, value=True)
    _call_compat(client.write_coil, address=COIL_EMERGENCY_STOP, value=False)
    _call_compat(client.write_coil, address=COIL_P201_AUTO, value=True)
    write_holding_reg(client, REG_LIT101_LEVEL, 500)
    write_holding_reg(client, REG_LIT201_LEVEL, 300)
    time.sleep(0.2)

    yield client

    # Teardown: ensure pumps are stopped and release HIL test override mode
    try:
        _call_compat(client.write_coil, address=COIL_TEST_OVERRIDE, value=False)
        pulse_coil(client, COIL_P101_STOP)
        pulse_coil(client, COIL_P102_STOP)
    except Exception:
        pass
    client.close()


def test_01_holding_registers_read_write(modbus_client):
    """Verify holding registers (%QW) can be written and read back deterministically."""
    test_level = 542
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, test_level)
    time.sleep(0.1)
    read_val = read_holding_reg(modbus_client, REG_LIT101_LEVEL)
    assert read_val == test_level, f"Expected register value {test_level}, got {read_val}"
    # Restore nominal operating level
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    time.sleep(0.1)


def test_02_pump_start_stop_latching(modbus_client):
    """Verify start/stop latching circuit for Raw Water Pump P101."""
    # Ensure nominal tank level
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    time.sleep(0.15)

    # 1. Pulse start button
    pulse_coil(modbus_client, COIL_P101_START)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P101_RUN) is True, "P101 failed to latch ON after Start pulse"

    # 2. Pulse stop button
    pulse_coil(modbus_client, COIL_P101_STOP)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P101_RUN) is False, "P101 failed to unlatch OFF after Stop pulse"


def test_03_high_high_cutoff_interlock(modbus_client):
    """Verify High-High tank level cutoff trips P101 and prevents restart."""
    # 1. Start P101 at normal level
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    time.sleep(0.15)
    pulse_coil(modbus_client, COIL_P101_START)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P101_RUN) is True, "Precondition failed: P101 must be running"

    # 2. Inject High-High tank level (920 mm >= 900 mm HH limit)
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 920)
    time.sleep(0.25)  # Allow 2 PLC scan cycles (200ms)

    # 3. Assert safety interlock tripped
    assert read_coil(modbus_client, COIL_ALARM_RAW_HH) is True, "Alarm High-High failed to assert"
    assert read_coil(modbus_client, COIL_P101_RUN) is False, "Safety Interlock Failed: P101 did not trip on HH level!"

    # 4. Attempt to start P101 while in High-High condition
    pulse_coil(modbus_client, COIL_P101_START)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P101_RUN) is False, "Safety Interlock Failed: P101 started during active HH alarm!"

    # 5. Restore safe level and clear alarm
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    time.sleep(0.2)
    assert read_coil(modbus_client, COIL_ALARM_RAW_HH) is False, "Alarm HH did not clear after level normalized"


def test_04_low_low_permissive_dry_run_interlock(modbus_client):
    """Verify Low-Low level permissive prevents Transfer Pump P102 dry running."""
    # 1. Inject Low-Low tank level (100 mm <= 150 mm LL limit)
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 100)
    time.sleep(0.25)

    # 2. Assert Low-Low alarm is active
    assert read_coil(modbus_client, COIL_ALARM_RAW_LL) is True, "Alarm Low-Low failed to assert"

    # 3. Attempt to start Transfer Pump P102
    pulse_coil(modbus_client, COIL_P102_START)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P102_RUN) is False, (
        "Safety Interlock Failed: Transfer Pump P102 started below Low-Low level!"
    )

    # 4. Restore safe level (500 mm)
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    time.sleep(0.2)
    assert read_coil(modbus_client, COIL_ALARM_RAW_LL) is False, "Alarm LL failed to clear"

    # 5. Now verify P102 starts when permissive is satisfied
    pulse_coil(modbus_client, COIL_P102_START)
    time.sleep(0.15)
    assert read_coil(modbus_client, COIL_P102_RUN) is True, "P102 failed to start when permissive was satisfied"

    # Clean up P102
    pulse_coil(modbus_client, COIL_P102_STOP)
    time.sleep(0.15)


def test_05_chemical_dosing_pump_pacing(modbus_client):
    """Verify Chemical Dosing Pump P201 paces automatically with Transfer Pump P102."""
    write_holding_reg(modbus_client, REG_LIT101_LEVEL, 500)
    _call_compat(modbus_client.write_coil, address=COIL_P201_AUTO, value=True)
    time.sleep(0.15)

    # Start Transfer Pump P102
    pulse_coil(modbus_client, COIL_P102_START)
    time.sleep(0.2)
    assert read_coil(modbus_client, COIL_P102_RUN) is True, "P102 failed to start"
    assert read_coil(modbus_client, COIL_P201_RUN) is True, "P201 failed to auto-pace with P102"

    # Stop Transfer Pump P102
    pulse_coil(modbus_client, COIL_P102_STOP)
    time.sleep(0.2)
    assert read_coil(modbus_client, COIL_P102_RUN) is False, "P102 failed to stop"
    assert read_coil(modbus_client, COIL_P201_RUN) is False, "P201 failed to stop when P102 stopped"


def run_standalone_cli():
    """Allows direct execution: python tests/test_ot_loop.py with formatted output."""
    print("=" * 72)
    print(" SWaT OT FOUNDATION & SAFETY INTERLOCK VERIFICATION SUITE")
    print(f" Target: OpenPLC Runtime at {OPENPLC_HOST}:{OPENPLC_PORT}")
    print("=" * 72)

    if ModbusTcpClient is None:
        print("[FAIL] pymodbus is not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    client = ModbusTcpClient(OPENPLC_HOST, port=OPENPLC_PORT, timeout=2.0)
    if not client.connect():
        print(f"[FAIL] Unable to connect to OpenPLC at {OPENPLC_HOST}:{OPENPLC_PORT}")
        print(" -> Ensure Docker container is running: 'docker compose up -d'")
        print(" -> Ensure swat_control.st has been uploaded and compiled in OpenPLC Web UI.")
        sys.exit(1)

    passed = 0
    failed = 0
    tests = [
        ("Register Read/Write Check", test_01_holding_registers_read_write),
        ("P101 Start/Stop Latching", test_02_pump_start_stop_latching),
        ("High-High Level Cutoff Interlock", test_03_high_high_cutoff_interlock),
        ("Low-Low Level Permissive Interlock", test_04_low_low_permissive_dry_run_interlock),
        ("Chemical Dosing Auto-Pacing", test_05_chemical_dosing_pump_pacing),
    ]

    try:
        # Pre-test initialization: engage HIL test override so simulator pauses register writes
        _call_compat(client.write_coil, address=COIL_TEST_OVERRIDE, value=True)
        _call_compat(client.write_coil, address=COIL_EMERGENCY_STOP, value=False)
        _call_compat(client.write_coil, address=COIL_P201_AUTO, value=True)
        write_holding_reg(client, REG_LIT101_LEVEL, 500)
        write_holding_reg(client, REG_LIT201_LEVEL, 300)
        time.sleep(0.3)

        for name, test_func in tests:
            try:
                test_func(client)
                print(f" [PASS] {name}")
                passed += 1
            except Exception as e:
                print(f" [FAIL] {name}: {e}")
                failed += 1
    finally:
        # Cleanup: disengage HIL test override and ensure pumps stopped
        try:
            _call_compat(client.write_coil, address=COIL_TEST_OVERRIDE, value=False)
            pulse_coil(client, COIL_P101_STOP)
            pulse_coil(client, COIL_P102_STOP)
        except Exception:
            pass
        client.close()

    print("-" * 72)
    print(f" Results: {passed} Passed, {failed} Failed out of {len(tests)} Tests.")
    print("=" * 72)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_standalone_cli()

