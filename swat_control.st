PROGRAM swat_control
  VAR
    (* --- Operator & Supervisory Commands (Modbus Coils %QX0.0 - %QX0.7) --- *)
    p101_start_cmd AT %QX0.0 : BOOL := FALSE; (* Infeed Raw Pump P101 Start Pulse *)
    p101_stop_cmd  AT %QX0.1 : BOOL := FALSE; (* Infeed Raw Pump P101 Stop Pulse *)
    p102_start_cmd AT %QX0.2 : BOOL := FALSE; (* Transfer Pump P102 Start Pulse *)
    p102_stop_cmd  AT %QX0.3 : BOOL := FALSE; (* Transfer Pump P102 Stop Pulse *)
    emergency_stop AT %QX0.4 : BOOL := FALSE; (* Master Emergency Stop *)
    p201_auto_mode AT %QX0.5 : BOOL := TRUE;  (* Chemical Dosing Pump P201 Auto Pacing *)

    (* --- Actuator Run Commands & Alarms (Modbus Coils %QX1.0 - %QX1.7) --- *)
    p101_run_cmd    AT %QX1.0 : BOOL := FALSE; (* Infeed Raw Water Pump P101 Run Output *)
    p102_run_cmd    AT %QX1.1 : BOOL := FALSE; (* Transfer Pump P102 Run Output *)
    p201_run_cmd    AT %QX1.2 : BOOL := FALSE; (* Chemical Dosing Pump P201 Run Output *)
    alarm_raw_hh    AT %QX1.3 : BOOL := FALSE; (* Raw Water Tank T101 High-High Cutoff Alarm *)
    alarm_raw_ll    AT %QX1.4 : BOOL := FALSE; (* Raw Water Tank T101 Low-Low Permissive Trip Alarm *)
    alarm_stage2_hh AT %QX1.5 : BOOL := FALSE; (* Stage 2 Tank T201 High-High Cutoff Alarm *)

    (* --- Analog Process Values from Simulator (Modbus Holding Registers %QW0 - %QW4) --- *)
    lit101_raw_level     AT %QW0 : INT := 500; (* Tank 1 Level (mm, 0-1000) *)
    lit201_stage2_level  AT %QW1 : INT := 300; (* Tank 2 Level (mm, 0-1000) *)
    fit101_raw_flow      AT %QW2 : INT := 0;   (* Inflow FIT101 (L/min, 0-300) *)
    fit201_transfer_flow AT %QW3 : INT := 0;   (* Transfer Flow FIT201 (L/min, 0-300) *)
    ait201_chemical_ppm  AT %QW4 : INT := 0;   (* Chemical Concentration AIT201 (ppm, 0-100) *)

    (* --- Safety Limit Setpoints (Modbus Holding Registers %QW5 - %QW7) --- *)
    raw_tank_hh_limit    AT %QW5 : INT := 900; (* T101 High-High Cutoff Threshold (mm) *)
    raw_tank_ll_limit    AT %QW6 : INT := 150; (* T101 Low-Low Permissive Threshold (mm) *)
    stage2_tank_hh_limit AT %QW7 : INT := 950; (* T201 High-High Cutoff Threshold (mm) *)
  END_VAR

  (* Setpoint sanity verification *)
  IF raw_tank_hh_limit <= 0 THEN
    raw_tank_hh_limit := 900;
  END_IF;
  IF raw_tank_ll_limit <= 0 THEN
    raw_tank_ll_limit := 150;
  END_IF;
  IF stage2_tank_hh_limit <= 0 THEN
    stage2_tank_hh_limit := 950;
  END_IF;

  (* ========================================================================= *)
  (* 1. Safety Interlocks & Alarms Evaluation                                   *)
  (* ========================================================================= *)
  
  (* Raw Water Tank High-High Cutoff Interlock *)
  IF lit101_raw_level >= raw_tank_hh_limit THEN
    alarm_raw_hh := TRUE;
  ELSE
    alarm_raw_hh := FALSE;
  END_IF;

  (* Raw Water Tank Low-Low Permissive Interlock (Dry Run Prevention) *)
  IF lit101_raw_level <= raw_tank_ll_limit THEN
    alarm_raw_ll := TRUE;
  ELSE
    alarm_raw_ll := FALSE;
  END_IF;

  (* Stage 2 Tank High-High Cutoff Interlock *)
  IF lit201_stage2_level >= stage2_tank_hh_limit THEN
    alarm_stage2_hh := TRUE;
  ELSE
    alarm_stage2_hh := FALSE;
  END_IF;

  (* ========================================================================= *)
  (* 2. Infeed Raw Water Pump P101 Latching & Cutoff Logic                      *)
  (* ========================================================================= *)
  (* Latching circuit: Trips immediately on Emergency Stop, Stop PB, or HH trip *)
  (* Start permissive: Level must be strictly below High-High cutoff limit      *)
  IF emergency_stop OR alarm_raw_hh OR p101_stop_cmd THEN
    p101_run_cmd := FALSE;
  ELSIF p101_start_cmd AND NOT alarm_raw_hh THEN
    p101_run_cmd := TRUE;
  END_IF;

  (* ========================================================================= *)
  (* 3. Transfer Pump P102 Latching & Low-Low Dry Run Permissive Logic         *)
  (* ========================================================================= *)
  (* Latching circuit: Trips immediately on Emergency Stop, Stop PB, LL trip,   *)
  (* or Stage 2 Tank HH overflow cutoff                                         *)
  (* Start permissive: Suction tank T101 must NOT be at Low-Low level           *)
  IF emergency_stop OR alarm_raw_ll OR alarm_stage2_hh OR p102_stop_cmd THEN
    p102_run_cmd := FALSE;
  ELSIF p102_start_cmd AND NOT alarm_raw_ll AND NOT alarm_stage2_hh THEN
    p102_run_cmd := TRUE;
  END_IF;

  (* ========================================================================= *)
  (* 4. Chemical Dosing Pump P201 Automated Pacing Logic                        *)
  (* ========================================================================= *)
  (* Paces dosing proportionally when Transfer Pump P102 is active              *)
  (* Stops immediately when Transfer Pump stops or on Emergency Stop            *)
  IF emergency_stop OR alarm_stage2_hh OR NOT p102_run_cmd THEN
    p201_run_cmd := FALSE;
  ELSIF p201_auto_mode AND p102_run_cmd THEN
    p201_run_cmd := TRUE;
  END_IF;

END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : swat_control;
  END_RESOURCE
END_CONFIGURATION

