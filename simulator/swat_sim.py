#!/usr/bin/env python3
"""
SWaT Continuous Water Treatment Plant Simulator (Stage 1 & Stage 2)
==================================================================

Physical Process Model:
-----------------------
- Stage 1 (Raw Water Intake & Storage):
  * Actuator: Raw Water Infeed Pump P101 (fills Tank T101)
  * Vessel: Raw Water Storage Tank T101 (Capacity: 1000 L, Level: 0-1000 mm)
  * Sensors: LIT101 (Level Transmitter), FIT101 (Inflow Transmitter)

- Stage 2 (Chemical Dosing & Water Transfer):
  * Actuators: 
      - Water Transfer Pump P102 (draws from T101, transfers into T201)
      - Chemical Dosing Pump P201 (injects coagulant into transfer line)
  * Vessel: Dosing & Clarifier Tank T201 (Capacity: 1000 L, Level: 0-1000 mm)
  * Sensors: LIT201 (Level Transmitter), FIT201 (Transfer Flow), AIT201 (Concentration)

Mass Balances:
--------------
Tank 1: dV1/dt = Qin_1(P101) - Qtrans(P102)
Tank 2: dV2/dt = Qtrans(P102) + Qdose(P201) - Qout_2(Process Demand)

Modbus/TCP Synchronization (OpenPLC Runtime v3):
-----------------------------------------------
- Reads Coils (%QX):
  * Coil 8  (%QX1.0): P101 Run Output
  * Coil 9  (%QX1.1): P102 Run Output
  * Coil 10 (%QX1.2): P201 Run Output
  * Coil 11 (%QX1.3): Alarm High-High T101
  * Coil 12 (%QX1.4): Alarm Low-Low T101
  * Coil 13 (%QX1.5): Alarm High-High T201

- Writes Holding Registers (%QW):
  * %QW0: LIT101 Raw Tank Level (mm)
  * %QW1: LIT201 Stage 2 Tank Level (mm)
  * %QW2: FIT101 Raw Infeed Flow (L/min)
  * %QW3: FIT201 Transfer Flow (L/min)
  * %QW4: AIT201 Chemical Concentration (ppm)
"""

import argparse
import logging
import math
import random
import sys
import time
from dataclasses import dataclass

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    ModbusTcpClient = None

# Configure structured industrial logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SWaT-Simulator")


@dataclass
class PlantState:
    """Represents the instantaneous physical state of the SWaT water plant."""
    t: float = 0.0                      # Total elapsed time (s)
    t101_volume: float = 500.0          # Liters (0 - 1000 L)
    t101_level: float = 500.0           # Millimeters (0 - 1000 mm)
    t201_volume: float = 300.0          # Liters (0 - 1000 L)
    t201_level: float = 300.0           # Millimeters (0 - 1000 mm)
    t201_chem_mass: float = 7.5         # Grams of active chemical in T201
    
    # Process flows (L/min)
    fit101_flow: float = 0.0            # Infeed raw flow
    fit201_flow: float = 0.0            # Transfer flow
    dose_flow: float = 0.0              # Dosing injection flow
    stage2_outflow: float = 0.0         # Downstream demand flow
    ait201_ppm: float = 25.0            # Chemical concentration in ppm (mg/L)
    
    # Actuator states (feedback from PLC)
    p101_running: bool = False
    p102_running: bool = False
    p201_running: bool = False
    
    # Safety Alarms (feedback from PLC)
    alarm_raw_hh: bool = False
    alarm_raw_ll: bool = False
    alarm_stage2_hh: bool = False


class SWaTPlantModel:
    """
    First-principles physical mass balance simulation engine.
    """
    def __init__(
        self,
        tank1_max_volume: float = 1000.0,
        tank2_max_volume: float = 1000.0,
        p101_nominal_flow_lps: float = 2.5,   # 150 L/min
        p102_nominal_flow_lps: float = 2.0,   # 120 L/min
        p201_nominal_flow_lps: float = 0.05,  # 3 L/min
        stage2_demand_lps: float = 1.2,       # 72 L/min continuous consumption
        initial_t101_level: float = 500.0,
        initial_t201_level: float = 300.0,
        noise_enabled: bool = True,
    ):
        self.v1_max = tank1_max_volume
        self.v2_max = tank2_max_volume
        self.p101_nom_lps = p101_nominal_flow_lps
        self.p102_nom_lps = p102_nominal_flow_lps
        self.p201_nom_lps = p201_nominal_flow_lps
        self.demand_lps = stage2_demand_lps
        self.noise_enabled = noise_enabled
        
        # Initialize plant state
        self.state = PlantState(
            t101_volume=max(0.0, min(self.v1_max, initial_t101_level)),
            t101_level=max(0.0, min(self.v1_max, initial_t101_level)),
            t201_volume=max(0.0, min(self.v2_max, initial_t201_level)),
            t201_level=max(0.0, min(self.v2_max, initial_t201_level)),
            t201_chem_mass=25.0 * (initial_t201_level / 1000.0), # 25 ppm baseline
        )

    def step(self, dt: float, p101_cmd: bool, p102_cmd: bool, p201_cmd: bool) -> PlantState:
        """
        Advance ODE fluid mass balances by dt seconds using Euler integration.
        """
        self.state.t += dt
        self.state.p101_running = p101_cmd
        self.state.p102_running = p102_cmd
        self.state.p201_running = p201_cmd
        
        # 1. Flow calculations (in Liters per second)
        # Raw infeed pump flow (P101)
        if p101_cmd:
            q_in_1 = self.p101_nom_lps
        else:
            q_in_1 = 0.0

        # Transfer pump flow (P102) requires suction fluid in T101
        if p102_cmd and self.state.t101_volume > 0.1:
            q_trans = self.p102_nom_lps
        else:
            q_trans = 0.0

        # Chemical dosing pump flow (P201)
        if p201_cmd:
            q_dose = self.p201_nom_lps
        else:
            q_dose = 0.0

        # Downstream Stage 2 process demand / outflow
        if self.state.t201_volume > 0.1:
            q_out_2 = self.demand_lps
        else:
            q_out_2 = 0.0

        # 2. Dynamic Fluid Mass Balance ODEs: dV/dt = Qin - Qout
        # Tank 1 Mass Balance
        dv1_dt = q_in_1 - q_trans
        new_v1 = self.state.t101_volume + dv1_dt * dt
        self.state.t101_volume = max(0.0, min(self.v1_max, new_v1))
        # 1 liter corresponds to 1 mm level in standard unit tank geometry
        self.state.t101_level = (self.state.t101_volume / self.v1_max) * 1000.0

        # Tank 2 Mass Balance
        dv2_dt = q_trans + q_dose - q_out_2
        new_v2 = self.state.t201_volume + dv2_dt * dt
        self.state.t201_volume = max(0.0, min(self.v2_max, new_v2))
        self.state.t201_level = (self.state.t201_volume / self.v2_max) * 1000.0

        # 3. Chemical Dosing Concentration Dynamics (ppm = mg/L)
        # Dosing concentrate is 10,000 mg/L (10 g/L)
        chem_dose_conc = 10000.0  # mg/L
        chem_added_mg = (q_dose * dt) * chem_dose_conc if p201_cmd else 0.0
        
        # Chemical removed by downstream process demand
        current_conc_mg_per_l = (
            (self.state.t201_chem_mass * 1000.0) / self.state.t201_volume
            if self.state.t201_volume > 1.0 else 0.0
        )
        chem_removed_mg = (q_out_2 * dt) * current_conc_mg_per_l
        
        new_chem_mass_mg = (self.state.t201_chem_mass * 1000.0) + chem_added_mg - chem_removed_mg
        self.state.t201_chem_mass = max(0.0, new_chem_mass_mg / 1000.0)

        if self.state.t201_volume > 1.0:
            self.state.ait201_ppm = (self.state.t201_chem_mass * 1000.0) / self.state.t201_volume
        else:
            self.state.ait201_ppm = 0.0

        # 4. Sensor Signal Formatting (L/min) with optional Gaussian noise
        noise_factor = 1.0
        if self.noise_enabled:
            # 0.5% standard deviation noise on flow sensors
            noise_factor = 1.0 + random.gauss(0.0, 0.005)

        self.state.fit101_flow = max(0.0, (q_in_1 * 60.0) * noise_factor)
        self.state.fit201_flow = max(0.0, (q_trans * 60.0) * noise_factor)
        self.state.dose_flow = q_dose * 60.0
        self.state.stage2_outflow = q_out_2 * 60.0

        return self.state


class OpenPLCModbusBridge:
    """
    Handles robust Modbus/TCP I/O synchronization with OpenPLC Runtime v3.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 502, slave_id: int = 1):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.client = None
        self.connected = False

    def connect(self) -> bool:
        if ModbusTcpClient is None:
            logger.error("pymodbus library is not installed in the environment!")
            return False

        if self.client is None:
            self.client = ModbusTcpClient(self.host, port=self.port, timeout=2.0)

        try:
            self.connected = self.client.connect()
            if self.connected:
                logger.info("Successfully connected to OpenPLC at %s:%d", self.host, self.port)
            return self.connected
        except Exception as e:
            logger.warning("Failed to connect to OpenPLC at %s:%d: %s", self.host, self.port, e)
            self.connected = False
            return False

    def _call_compat(self, func, *args, **kwargs):
        """Dispatches pymodbus method trying device_id, slave, and unit for full version agility."""
        for kw in ("device_id", "slave", "unit"):
            try:
                return func(*args, **{kw: self.slave_id}, **kwargs)
            except TypeError:
                continue
        return func(*args, **kwargs)

    def read_actuators_and_alarms(self):
        """
        Reads actuator run coils and test override status (%QX0.6 -> coil 6, %QX1.0 - %QX1.5 -> coils 8 to 13).
        Returns:
            p101_run, p102_run, p201_run, alarm_hh, alarm_ll, alarm_s2_hh, test_override
        """
        if not self.connected:
            return False, False, False, False, False, False, False

        try:
            rr = self._call_compat(self.client.read_coils, address=0, count=14)
            if rr is None or rr.isError():
                logger.warning("Modbus read coils error: %s", rr)
                self.connected = False
                return False, False, False, False, False, False, False
            
            bits = rr.bits
            test_override = bool(bits[6])
            p101_run = bool(bits[8])
            p102_run = bool(bits[9])
            p201_run = bool(bits[10])
            alarm_hh = bool(bits[11])
            alarm_ll = bool(bits[12])
            alarm_s2_hh = bool(bits[13])
            return p101_run, p102_run, p201_run, alarm_hh, alarm_ll, alarm_s2_hh, test_override
        except Exception as e:
            logger.warning("Exception during Modbus read: %s", e)
            self.connected = False
            return False, False, False, False, False, False, False

    def read_sensor_registers(self):
        """Reads holding registers %QW0 and %QW1 during HIL test override."""
        if not self.connected:
            return None, None
        try:
            rr = self._call_compat(self.client.read_holding_registers, address=0, count=2)
            if rr and not rr.isError():
                return float(rr.registers[0]), float(rr.registers[1])
            return None, None
        except Exception:
            return None, None

    def write_sensor_registers(self, lit101: float, lit201: float, fit101: float, fit201: float, ait201: float):
        """
        Writes sensor measurements into OpenPLC Holding Registers (%QW0 - %QW4).
        """
        if not self.connected:
            return False

        try:
            # Scaled 16-bit integers
            reg_values = [
                int(round(lit101)),
                int(round(lit201)),
                int(round(fit101)),
                int(round(fit201)),
                int(round(ait201)),
            ]
            rq = self._call_compat(self.client.write_registers, address=0, values=reg_values)
            if rq is None or rq.isError():
                logger.warning("Modbus write registers error: %s", rq)
                self.connected = False
                return False
            return True
        except Exception as e:
            logger.warning("Exception during Modbus write: %s", e)
            self.connected = False
            return False

    def close(self):
        if self.client:
            self.client.close()
            self.connected = False


def run_simulation(args):
    """
    Main real-time simulation synchronization loop.
    """
    logger.info("Initializing SWaT Plant Simulation Engine...")
    logger.info("Mode: %s", "STANDALONE LOCAL PHYSICS" if args.standalone else "OPENPLC MODBUS SYNCHRONIZED")
    
    plant = SWaTPlantModel(
        initial_t101_level=args.initial_level,
        noise_enabled=not args.deterministic,
    )
    bridge = OpenPLCModbusBridge(host=args.host, port=args.port, slave_id=args.slave)
    
    dt = args.dt
    log_period = args.log_interval
    last_log_time = 0.0
    
    logger.info("Simulation loop running at %.1f Hz (dt = %.3f s)", 1.0 / dt, dt)
    
    try:
        while True:
            cycle_start = time.time()
            
            # --- 1. Actuator Input Resolution ---
            if args.standalone:
                # Standalone simulation heuristic: run infeed when low, transfer when safe
                p101_cmd = plant.state.t101_level < 850.0
                p102_cmd = plant.state.t101_level > 200.0 and plant.state.t201_level < 800.0
                p201_cmd = p102_cmd
                alarm_hh = plant.state.t101_level >= 900.0
                alarm_ll = plant.state.t101_level <= 150.0
                alarm_s2_hh = plant.state.t201_level >= 950.0
                test_override = False
            else:
                if not bridge.connected:
                    bridge.connect()
                
                if bridge.connected:
                    (
                        p101_cmd,
                        p102_cmd,
                        p201_cmd,
                        alarm_hh,
                        alarm_ll,
                        alarm_s2_hh,
                        test_override,
                    ) = bridge.read_actuators_and_alarms()
                else:
                    # Keep previous or fail-safe pump commands if connection is down
                    p101_cmd, p102_cmd, p201_cmd = False, False, False
                    alarm_hh, alarm_ll, alarm_s2_hh = False, False, False
                    test_override = False

            # --- 2. Advance Fluid Mass Balances ---
            if test_override:
                # In test override mode, sync physical state to the externally injected test values
                inj_lit101, inj_lit201 = bridge.read_sensor_registers()
                if inj_lit101 is not None:
                    plant.state.t101_level = inj_lit101
                    plant.state.t101_volume = inj_lit101
                if inj_lit201 is not None:
                    plant.state.t201_level = inj_lit201
                    plant.state.t201_volume = inj_lit201
                state = plant.state
                state.p101_running = p101_cmd
                state.p102_running = p102_cmd
                state.p201_running = p201_cmd
            else:
                state = plant.step(dt=dt, p101_cmd=p101_cmd, p102_cmd=p102_cmd, p201_cmd=p201_cmd)

            state.alarm_raw_hh = alarm_hh
            state.alarm_raw_ll = alarm_ll
            state.alarm_stage2_hh = alarm_s2_hh

            # --- 3. Synchronize Sensors to OpenPLC Registers ---
            # ONLY write to registers when NOT in HIL test override mode
            if not args.standalone and bridge.connected and not test_override:
                bridge.write_sensor_registers(
                    lit101=state.t101_level,
                    lit201=state.t201_level,
                    fit101=state.fit101_flow,
                    fit201=state.fit201_flow,
                    ait201=state.ait201_ppm,
                )

            # --- 4. Structured Operational Telemetry Output ---
            if (state.t - last_log_time) >= log_period:
                last_log_time = state.t
                p101_str = "RUN" if state.p101_running else "OFF"
                p102_str = "RUN" if state.p102_running else "OFF"
                p201_str = "RUN" if state.p201_running else "OFF"
                
                alarms = []
                if state.alarm_raw_hh:
                    alarms.append("T101_HIGH_HIGH")
                if state.alarm_raw_ll:
                    alarms.append("T101_LOW_LOW")
                if state.alarm_stage2_hh:
                    alarms.append("T201_HIGH_HIGH")
                alarm_str = ", ".join(alarms) if alarms else "NOMINAL"
                
                if test_override:
                    conn_str = "HIL:TEST_MODE"
                elif args.standalone:
                    conn_str = "STANDALONE"
                else:
                    conn_str = "PLC:ONLINE" if bridge.connected else "PLC:WAITING"
                
                logger.info(
                    "[%s] T101: %5.1f mm | T201: %5.1f mm | P101:%s (FIT101:%5.1f L/m) | P102:%s (FIT201:%5.1f L/m) | P201:%s | Chem:%4.1f ppm | Alarms:[%s]",
                    conn_str,
                    state.t101_level,
                    state.t201_level,
                    p101_str,
                    state.fit101_flow,
                    p102_str,
                    state.fit201_flow,
                    p201_str,
                    state.ait201_ppm,
                    alarm_str,
                )

            # --- 5. Precise Real-Time Loop Timing ---
            elapsed = time.time() - cycle_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Simulation stopped by operator.")
    finally:
        bridge.close()
        logger.info("Modbus bridge terminated.")


def parse_arguments():
    parser = argparse.ArgumentParser(description="SWaT Continuous Industrial Plant Simulator")
    parser.add_argument("--host", default="127.0.0.1", help="OpenPLC Modbus server IP address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=502, help="OpenPLC Modbus TCP port (default: 502)")
    parser.add_argument("--slave", type=int, default=1, help="Modbus slave ID / unit ID (default: 1)")
    parser.add_argument("--dt", type=float, default=0.1, help="Simulation time step in seconds (default: 0.1s -> 10Hz)")
    parser.add_argument("--log-interval", type=float, default=1.0, help="Console telemetry logging interval (default: 1.0s)")
    parser.add_argument("--initial-level", type=float, default=500.0, help="Initial level for T101 in mm (default: 500)")
    parser.add_argument("--standalone", action="store_true", help="Run in standalone physical simulation mode without Modbus connection")
    parser.add_argument("--deterministic", action="store_true", help="Disable stochastic sensor noise for deterministic testing")
    return parser.parse_args()


if __name__ == "__main__":
    run_simulation(parse_arguments())

