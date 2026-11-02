# Hardware & Integration Space

This directory contains wiring schematics, calibration matrices, and mechanical assembly notes for **Mix 1 (Hardware/Software Integrator)** and **Mix 2 (Hardware & Assembly Lead)**.

## Quick Reference Checklists

### Mix 1 (Integration & Calibration)
- [ ] ESP32 USB-CDC communication & JSON validation on `/dev/ttyUSB0`
- [ ] MaixCam UART link on `/dev/ttyAMA0` (115200 baud, 8N1)
- [ ] Mecanum wheel PWM trim calibration for straight-line strafing
- [ ] MG995R servo end-stop calibration for soil probe rack-and-pinion
- [ ] 5V relay switching and pump prime check

### Mix 2 (Mechanical & Electrical Assembly)
- [ ] 4x DC motor mounting and Mecanum **Top-Down 'X' Roller Configuration**
- [ ] 12V LiPo battery power matrix wiring with 10A fuse and kill switch
- [ ] Buck 1 (5.1V logic) and Buck 2 (5.0V actuator) isolation with shared star ground
- [ ] 3D-printed rack-and-pinion probe mechanism assembly
- [ ] Fluid tank, pump, check valve, and tubing plumbing
