# Hardware & Integration Space (6WD Skid-Steer Architecture)

This directory contains wiring schematics, calibration matrices, and mechanical assembly notes for **Mix 1 (Hardware/Software Integrator)** and **Mix 2 (Hardware & Assembly Lead)**.

## Quick Reference Checklists

### Mix 1 (Integration & Calibration)
- [ ] ESP32 USB-CDC communication & JSON validation on `/dev/ttyUSB0` (115200 baud)
- [ ] MaixCam UART link on `/dev/ttyAMA0` (115200 baud, 8N1)
- [ ] BTS7960 PWM duty-cycle and trim tuning ($K_{LEFT}, K_{RIGHT}$) for straight forward skid-steer tracking
- [ ] Skid-turn PWM calibration for smooth zero-radius turning without brownouts
- [ ] PCA9685 servo angle limits for 2x MG995R servos (rack-and-pinion vertical plunge & deployment)
- [ ] 5V relay switching, check valve direction, and pump delivery pressure check

### Mix 2 (Mechanical & Electrical Assembly)
- [ ] 6WD Acrylic Curious Rover Chassis construction and secure mounting of all 6 DC gearmotors
- [ ] Parallel wiring of 3x Left motors to BTS7960 Driver 1 (M+ and M- terminals)
- [ ] Parallel wiring of 3x Right motors to BTS7960 Driver 2 (M+ and M- terminals)
- [ ] 12V LiPo battery power matrix wiring with 20A master fuse and emergency kill switch
- [ ] Buck 1 (5.1V logic) and Buck 2 (5.0V actuator) voltage adjustment with star ground
- [ ] 3D-printed rack-and-pinion probe mechanism assembly with 2x MG995R servos
- [ ] Water reservoir tank mounting, 5V submersible pump placement, and silicone tubing routing
