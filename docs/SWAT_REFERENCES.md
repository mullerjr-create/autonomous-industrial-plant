# Academic & Industrial Provenance: SWaT Plant Reference Documentation
**Document ID:** SWaT-DOC-REF-001  
**Origin:** iTrust, Centre for Research in Cyber Security, Singapore University of Technology and Design (SUTD)  
**Revision:** 1.0.0  

---

## 1. Primary Academic & Technical References

The instrumentation tags, physical process parameters, control invariants, and attack surface modeled in this repository are based on the **Secure Water Treatment (SWaT)** operational testbed designed and constructed by **iTrust at the Singapore University of Technology and Design (SUTD)**.

### Foundational Publications

1. **Testbed Architecture & Operational Design:**
   - **Authors:** Aditya P. Mathur and Nils Ole Tippenhauer
   - **Title:** *"SWaT: A water treatment testbed for research and training on ICS security"*
   - **Conference:** 2016 International Workshop on Cyber-physical Systems for Smart Water Networks (CySWater), Vienna, Austria, 2016, pp. 31-36.
   - **DOI:** [10.1109/CySWater.2016.7469060](https://doi.org/10.1109/CySWater.2016.7469060)
   - **Significance:** First comprehensive architectural publication detailing the six operational stages, Allen-Bradley PLCs, physical tank dimensions, chemical dosing subsystems, and communications network.

2. **Dataset & Physical Process Dynamics:**
   - **Authors:** Jonathan Goh, Sridhar Adepu, Khurum Nazir Junejo, and Aditya Mathur
   - **Title:** *"A Dataset to Support Research in the Design of Secure Water Treatment Systems"*
   - **Book:** Critical Information Infrastructures Security (CRITIS 2016). Lecture Notes in Computer Science, vol 10242. Springer, Cham.
   - **DOI:** [10.1007/978-3-319-71368-7_8](https://doi.org/10.1007/978-3-319-71368-7_8)
   - **Significance:** Details the 51 physical sensors and actuators across all six stages, normal baseline operating profiles, and sensor ranges.

3. **Attack Invariants & Physical Interlock Logic:**
   - **Authors:** Sridhar Adepu and Aditya Mathur
   - **Title:** *"Using anomaly detection for a water treatment system"*
   - **Conference:** Proceedings of the 2nd ACM Workshop on Cyber-Physical Systems Security and Resilience (CPS-SR '16), pp. 43–48.
   - **DOI:** [10.1145/2897036.2897044](https://doi.org/10.1145/2897036.2897044)
   - **Significance:** Formalizes the physical invariants:
     - $LIT101 \ge 800\text{ mm} \implies MV101\text{ is CLOSED}$
     - $LIT101 \le 500\text{ mm} \implies MV101\text{ is OPEN}$
     - $LIT101 \le 250\text{ mm} \implies P101 / P102\text{ must TRIP (Dry-run protection)}$

4. **Official SUTD iTrust Testbed Repository:**
   - **Institution:** Singapore University of Technology and Design (SUTD)
   - **Center:** iTrust Centre for Research in Cyber Security
   - **URL:** [https://itrust.sutd.edu.sg/itrust-labs_datasets/dataset_info/](https://itrust.sutd.edu.sg/itrust-labs_datasets/dataset_info/)

---

## 2. Process Tag Concordance: SUTD Physical SWaT vs. Local Digital Twin

The table below documents how the tags in this repository map to the physical SUTD SWaT facility:

| Tag Name | SUTD SWaT Physical Testbed Definition | In This Local Implementation | Exact Match? |
| :--- | :--- | :--- | :---: |
| **T101** | Stage 1 Raw Water Storage Tank | Modeled as 1,000 L buffer tank in `swat_sim.py` | **Yes** |
| **LIT101** | Level Indicator Transmitter on Tank T101 | Ultrasonic/DP level transmitter (%QW0) | **Yes** |
| **FIT101** | Flow Indicator Transmitter on Raw Infeed | Magnetic flow meter on infeed pipe (%QW2) | **Yes** |
| **MV101** | Motorized Valve controlling city infeed | Replaced by active Infeed Pump `P101` | *Adapted* |
| **P101** | Raw Water Transfer Pump 1 (Duty) | Infeed Supply Pump (%QX0.0, %QX1.0) | **Yes** |
| **P102** | Raw Water Transfer Pump 2 (Standby) | Transfer Pump T101 &rarr; T201 (%QX0.2, %QX1.1) | **Yes** |
| **T201** | Stage 2 Chemical Dosing / Contact Tank | Modeled as 1,000 L mixing vessel in `swat_sim.py` | **Yes** |
| **LIT201** | Level Indicator Transmitter on Tank T201 | Ultrasonic/DP level transmitter (%QW1) | **Yes** |
| **FIT201** | Flow Indicator Transmitter on Transfer Line | Magnetic flow meter into Stage 2 (%QW3) | **Yes** |
| **P201** | Chemical Dosing Pump (Coagulant / NaOCl) | Diaphragm dosing pump (%QX0.5, %QX1.2) | **Yes** |
| **AIT201** | Water Quality Analyzer (Conductivity / pH / PPM)| Analyzer Transmitter (%QW4) | **Yes** |
| **HH Limit**| High-High level cutoff threshold (800–1000 mm) | Configurable setpoint register `%QW5` (900 mm) | **Yes** |
| **LL Limit**| Low-Low dry-run permissive threshold (150–250 mm)| Configurable setpoint register `%QW6` (150 mm) | **Yes** |

*Note on Physical vs. Virtual Plant:*  
In the physical Singapore facility, water enters Stage 1 from the municipal water utility header through motorized valve `MV101`. In our standalone digital twin, we equipped the infeed line with pump `P101` so that the model can run self-contained closed-loop pumping cycles without requiring an external pressurized water source.

---

## 3. What Was Authored for This Project vs. What Was Published

To be completely transparent about authorship and provenance:

1. **What is from SUTD iTrust (The Source Literature):**
   - The process design (Stage 1 raw water storage & Stage 2 chemical pre-treatment).
   - The instrument tag names (`LIT101`, `FIT101`, `P101`, `P102`, `P201`, `AIT201`, `T101`, `T201`).
   - The physical mass balance equations ($dV/dt = Q_{in} - Q_{out}$).
   - The control invariants (High-High overflow cutoffs, Low-Low pump dry-run permissives, proportional chemical dosing).

2. **What Was Authored Specifically for This Project:**
   - **`docs/PID_SPECIFICATION.md`:** Authored as a formal ANSI/ISA-5.1 specification document so that software engineers have a clean engineering reference without needing to read 5 academic papers.
   - **`docs/CONTROL_PHILOSOPHY.md`:** Authored as an IEC 61131-3 Functional Design Specification detailing the exact memory addresses, scan cycles, and cause-and-effect matrix used by OpenPLC Runtime v3.
   - **`docs/STANDARD_OPERATING_PROCEDURES.md`:** Authored as an operational manual (SOP-001 through SOP-008) guiding plant startup, steady-state monitoring, shutdown, E-Stop recovery, and HIL testing.
   - **`plc/swat_control.st`:** The IEC 61131-3 Structured Text implementation running on OpenPLC.
   - **`simulator/swat_sim.py`:** The real-time ODE simulation daemon running at 10 Hz over Modbus/TCP.

Neither SUTD nor any other party provided pre-written Markdown documentation files for this repo; they were engineered based on the official peer-reviewed SWaT specifications cited above.

