# CHIP TO CROP 2.0 — PrecisionRover Engineering Master (6WD Edition)

Comprehensive workspace, system architecture, and development tracker for the "PrecisionRover" autonomous agricultural robotics platform built for the **CHIP TO CROP 2.0** hackathon.

---

## System Architecture & Communication Flow
- **The Vision Edge:** MaixCam handles AI plant detection and alignment logic. It sends simple movement commands (Left, Right, Center) to the Pi 5 via **UART Serial**.
- **The Sensor Hub:** An ESP32-S3 reads all physical environment sensors (Ultrasonic, Soil Moisture, Turbidity). It bundles this data into a JSON packet and streams it to the Pi 5 via **USB Serial**.
- **The Core Orchestrator:** The Raspberry Pi 5 acts as the central brain. It receives JSON from the ESP32-S3 and strings from the MaixCam, calculates the skid-steer kinematics, drives the BTS7960 motors, triggers the 5V pump, and pushes the final telemetry to the cloud via MQTT.

### Hardware & Data Flow Map

```mermaid
flowchart TD
    subgraph PowerSystem ["Power Distribution Network"]
        LIPO["12V 3S LiPo Battery (11.1V - 12.6V)"]
        KILL["Master Kill Switch / 20A Fuse"]
        BUCK1["5V 5A Buck Converter (Logic Rail)"]
        BUCK2["5V 5A Buck Converter (Actuation Rail)"]
        
        LIPO --> KILL
        KILL -->|12V High-Current Bus| BTS_L["BTS7960 Driver L (3x Left Motors in Parallel)"]
        KILL -->|12V High-Current Bus| BTS_R["BTS7960 Driver R (3x Right Motors in Parallel)"]
        KILL --> BUCK1
        KILL --> BUCK2
    end

    subgraph Tier1_Compute ["Central Orchestrator (Raspberry Pi 5)"]
        PI["Raspberry Pi 5 (8GB)"]
        MQTT_PUB["MQTT Client & Skid-Steer FSM"]
    end

    subgraph Tier2_Vision ["Edge Vision Node (MaixCam)"]
        MAIX["Sipeed MaixCam (K230 NPU)"]
        CAM["Onboard Camera Sensor"]
        CAM --> MAIX
    end

    subgraph Tier3_Sensors ["Analog & Environment Sensor Hub (ESP32-S3)"]
        ESP["ESP32-S3 Dev Module"]
        SOIL["Capacitive Soil Moisture Sensor"]
        TURB["Turbidity Sensor (Water Tank)"]
        US["HC-SR04 Ultrasonic Sensor"]
        SOIL -->|ADC1 GPIO 1| ESP
        TURB -->|ADC1 GPIO 2| ESP
        US -->|GPIO 4 (Trig) / GPIO 5 (Echo)| ESP
    end

    subgraph Actuators ["Actuators & Mechanisms"]
        PCA["PCA9685 16-Ch I2C PWM Driver"]
        SERVO1["MG995R Servo 1 (Probe Rack & Pinion)"]
        SERVO2["MG995R Servo 2 (Probe Deployment)"]
        RELAY["5V Single-Channel Relay Module"]
        PUMP["5V Submersible Water Pump"]
        MOTORS_L["3x Left DC Gearmotors (Skid-Steer)"]
        MOTORS_R["3x Right DC Gearmotors (Skid-Steer)"]
        
        PCA --> SERVO1
        PCA --> SERVO2
        RELAY --> PUMP
    end

    %% Power Routing
    BUCK1 -->|5V / 3A USB-C| PI
    BUCK1 -->|5V VCC| ESP
    BUCK1 -->|5V VCC| MAIX
    BUCK2 -->|5V Servo Rail V+| PCA
    BUCK2 -->|5V NO Contact| RELAY

    %% Data Connections
    MAIX -->|UART TX/RX @ 115200 Baud| PI
    ESP -->|USB CDC Serial (JSON Telemetry) @ 115200 Baud| PI
    PI -->|I2C SDA/SCL - Bus 1| PCA
    PI -->|GPIO Output| RELAY
    PI -->|RPWM / LPWM / R_EN / L_EN| BTS_L
    PI -->|RPWM / LPWM / R_EN / L_EN| BTS_R
    BTS_L --> MOTORS_L
    BTS_R --> MOTORS_R
    PI --> MQTT_PUB
    MQTT_PUB -->|WiFi / WebSockets| DASHBOARD["Streamlit Dashboard / Cloud Broker"]
```

### Decoupled Software Architecture

```
+-----------------------------------------------------------------------------+
|                           RASPBERRY PI 5 (Host)                            |
|                                                                             |
|  +------------------------+  +-------------------+  +--------------------+  |
|  |     MaixCam UART       |  |  ESP32 USB-Serial |  | Ultrasonic Thread  |  |
|  |    Listener Thread     |  |  Listener Thread  |  |  (Obstacle Avoid)  |  |
|  +-----------+------------+  +---------+---------+  +---------+----------+  |
|              |                         |                      |             |
|              | (Vision Commands)       | (JSON Telemetry)     | (Distance)  |
|              v                         v                      v             |
|  +-----------------------------------------------------------------------+  |
|  |                  CENTRAL FINITE STATE MACHINE (FSM)                   |  |
|  |       [IDLE] -> [SEARCHING] -> [STEERING/ALIGNING] -> [PROBING] ...   |  |
|  +-----------------------------------------------------------------------+  |
|              |                         |                      |             |
|              v                         v                      v             |
|  +------------------------+  +-------------------+  +--------------------+  |
|  | 6WD Skid-Steer Engine  |  | Actuator Driver   |  |  MQTT Telemetry   |  |
|  |  (Dual BTS7960 PWM/EN) |  | (PCA9685/Relay)   |  |   Publisher Hub    |  |
|  +------------------------+  +-------------------+  +--------------------+  |
+-----------------------------------------------------------------------------+
```

### Power Distribution Matrix

| Rail | Source | Regulated Voltage | Max Amperage | Components Powered |
| :--- | :--- | :--- | :--- | :--- |
| **High-Current 12V** | 12V 3S LiPo Battery | Direct Unregulated (11.1V - 12.6V) | 30A Peak (20A Fuse) | 2x BTS7960 Motor Drivers $\rightarrow$ 6x DC Motors (3 parallel per side) |
| **Logic 5V Rail** | 12V LiPo via Buck Converter 1 | 5.1V DC | 5.0A | Raspberry Pi 5, MaixCam, ESP32 |
| **Actuation 5V Rail** | 12V LiPo via Buck Converter 2 | 5.0V DC | 5.0A | PCA9685 V+ Rail (2x MG995R Servos), 5V Relay + Water Pump |

> **Safety Warning:** Logic 5V and Actuator 5V positive lines must remain strictly isolated to prevent high-surge servo stalls or pump induction spikes from crashing the Pi 5. Common star ground must be tied across all devices and the battery negative terminal.

---

## Dev 1 Space (Core Orchestrator - Pi 5)

### Responsibilities
* Implement **6WD Skid-Steer (Tank Drive)** kinematics with differential speed/direction control using **2x BTS7960 high-current motor drivers**.
* Drive the PCA9685 16-channel servo driver over I2C to control the 2x MG995R servos for probe depth and deployment.
* Toggle the 5V water pump relay for targeted micro-irrigation based on telemetry triggers.
* Run non-blocking background serial reader threads for MaixCam UART (`/dev/ttyAMA0`) and ESP32 USB CDC (`/dev/ttyUSB0`).
* Maintain HC-SR04 ultrasonic obstacle scanning and execute the central Finite State Machine (FSM).
* Publish real-time telemetry packets over MQTT (`precisionrover/telemetry`).

### Task Checklist
- [ ] Configure Raspberry Pi OS to enable hardware I2C-1 and UART0 (`ttyAMA0`).
- [ ] Install software stack: `pyserial`, `paho-mqtt`, `smbus2`, `adafruit-circuitpython-pca9685`, `gpiozero`.
- [ ] L298N/BTS7960 Skid-Steer control, PCA9685 servo control, Dual 5V relay control for Water and Fertilizer pumps.
- [ ] Implement BTS7960 driver control class (RPWM, LPWM, R_EN, L_EN) for left and right motor banks.
- [ ] Implement 6WD Skid-Steer Kinematics matrix:
  * **Forward:** Both Left and Right banks drive forward.
  * **Reverse:** Both Left and Right banks drive backward.
  * **Steer Left:** Left bank reverses / slows, Right bank drives forward (skid-turn).
  * **Steer Right:** Right bank reverses / slows, Left bank drives forward (skid-turn).
  * **Stop:** Active brake by holding LPWM/RPWM low and disabling EN pins.
- [ ] Integrate HC-SR04 ultrasonic ranging thread with safety stop when obstacle distance $< 20\text{ cm}$.
- [ ] Configure PCA9685 I2C driver for 2x MG995R servos (rack-and-pinion vertical plunge + probe articulation).
- [ ] Configure GPIO pin for 5V water pump relay trigger.
- [ ] Build thread-safe FIFO queues for vision commands and sensor telemetry.
- [ ] Implement Rover FSM transitions: `SEARCHING` $\rightarrow$ `ALIGNING` $\rightarrow$ `PROBING` $\rightarrow$ `IRRIGATING` $\rightarrow$ `RETRACTING`.
- [ ] Publish formatted JSON telemetry payloads to local/cloud MQTT broker.

**Primary Codefile:** `Pi5-Orchestrator/main_loop.py`

---

## Dev 2 Space (Vision AI - MaixCam)

### Responsibilities
* Deploy edge vision model (YOLOv8n / K230 `.kmodel` or OpenCV color segmentation) on the Sipeed MaixCam.
* Detect target crops/plants and compute the horizontal center offset relative to the frame.
* Segment the frame into deadband and steering zones to generate skid-steer navigation directives.
* Transmit single-line ASCII steering directives (`STEER_LEFT`, `STEER_RIGHT`, `ALIGNED_STOP`, `NO_TARGET`) over hardware UART at 115200 baud with hysteresis filtering.

### Task Checklist
- [ ] Boot and verify MaixPy v4 environment on Sipeed MaixCam.
- [ ] Calibrate camera exposure and white balance for greenhouse and outdoor illumination.
- [ ] Define horizontal image coordinate zones ($W = 640\text{ px}$):
  * **Left Zone:** $X \in [0, 260)$ $\rightarrow$ `STEER_LEFT`
  * **Center Deadband:** $X \in [260, 380]$ $\rightarrow$ `ALIGNED_STOP`
  * **Right Zone:** $X \in (380, 640]$ $\rightarrow$ `STEER_RIGHT`
- [ ] Implement multi-frame stability filter (minimum 3 consecutive frames before command switch) to prevent oscillation.
- [ ] Output ASCII directives over UART (`/dev/ttyS0` @ 115200 baud).
- [ ] Render HUD overlay (bounding box, centroid crosshair, deadband boundaries, active command) on onboard display.

**Primary Codefile:** `MaixCam-Vision/vision_tracking.py`

---

## Dev 3 Space (Sensor Hub & Cloud - ESP32-S3 + UI)

### Responsibilities
* Sample analog capacitive soil moisture sensor and turbidity sensor via ESP32-S3 12-bit ADC (ADC1 channels).
* Read HC-SR04 ultrasonic distance sensor to provide front obstacle clearance.
* Clean raw analog signals with an Exponential Moving Average (EMA) low-pass filter to reject electrical motor noise.
* Stream structured single-line JSON telemetry packets over USB CDC Serial at 10 Hz.
* Host Mosquitto MQTT broker on Raspberry Pi and build an interactive Streamlit mission dashboard.

### Task Checklist
- [ ] Configure ESP32-S3 pins: GPIO 1 (Soil Moisture ADC1), GPIO 2 (Turbidity ADC1), GPIO 4 (Sonar Trig), GPIO 5 (Sonar Echo).
- [ ] Perform two-point calibration for capacitive soil probe: dry air threshold (`SOIL_RAW_AIR`) and saturated water (`SOIL_RAW_WATER`).
- [ ] Calibrate turbidity voltage-to-NTU characteristic curve.
- [ ] Implement digital smoothing filter: $V_{filtered} = \alpha \cdot V_{raw} + (1 - \alpha) \cdot V_{prev}$.
- [ ] Measure HC-SR04 pulse travel time and convert to distance in centimeters.
- [ ] Format and push single-line JSON strings: `{"distance_cm": float, "soil_moisture_pct": float, "turbidity_ntu": float, "turb_v": float}`.
- [ ] Set up local Mosquitto MQTT broker on Raspberry Pi 5.
- [ ] Develop Streamlit web dashboard (`dashboard_app.py`) featuring live KPI cards, historical moisture/turbidity charts, and FSM status.

**Primary Codefile:** `ESP32-SensorHub/esp32_sensors.ino`  
**Dashboard App:** `ESP32-SensorHub/dashboard_app.py`

---

## Mix 1 Space (Hardware/Software Integrator)

### Responsibilities
* Verify inter-board communications (Pi 5 $\leftrightarrow$ ESP32 USB CDC, Pi 5 $\leftrightarrow$ MaixCam UART).
* Perform BTS7960 skid-steer tuning and PWM duty cycle calibration to compensate for track/side resistance differences.
* Calibrate PCA9685 servo pulse widths for 2x MG995R servos to guarantee proper ground penetration without stalling.
* Conduct complete hardware-in-the-loop (HIL) integration runs.

### Task Checklist
- [ ] Validate ESP32 USB CDC telemetry stream on `/dev/ttyUSB0` at 115200 baud.
- [ ] Validate MaixCam UART steering commands on `/dev/ttyAMA0` with logic analyzer or serial monitor.
- [ ] Tune BTS7960 PWM duty cycles ($K_{LEFT}, K_{RIGHT}$) for straight forward driving on 6WD skid-steer chassis.
- [ ] Tune skid-turn duty cycles for smooth rotation without brownouts.
- [ ] Set safe angular travel limits on PCA9685 for Servo 1 and Servo 2 to prevent mechanical binding.
- [ ] Verify 5V relay switching and test pump delivery pressure and nozzle targeting.
- [ ] Perform full autonomous mission trial: Plant detection $\rightarrow$ skid-steer alignment $\rightarrow$ probe descent $\rightarrow$ moisture read $\rightarrow$ automated irrigation.

---

## Mix 2 Space (Hardware & Assembly Lead)

### Responsibilities
* Mechanical assembly of the **6WD Acrylic Curious Rover Chassis** with 6x DC gearmotors (No coding).
* Parallel electrical wiring connecting 3x Left motors to BTS7960 Driver 1 and 3x Right motors to BTS7960 Driver 2.
* Power distribution wiring: 12V LiPo battery, 20A master fuse, kill switch, and dual 5V buck converters.
* Mechanical assembly and alignment of the 2x MG995R rack-and-pinion soil probe mechanism.
* Fluid plumbing for 5V water pump, reservoir tank, one-way check valve, and delivery tubing.
* Cable harness routing, strain relief, and heat shrink insulation.

### Task Checklist
- [ ] Assemble 6WD Acrylic Curious Rover Chassis with all 6 DC gearmotors firmly secured.
- [ ] Wire the 3 Left motors in parallel to BTS7960 Driver 1 (M+ and M- terminals) with matched polarity.
- [ ] Wire the 3 Right motors in parallel to BTS7960 Driver 2 (M+ and M- terminals) with matched polarity.
- [ ] Mount dual BTS7960 motor driver modules on insulated standoffs with heat sinks accessible to airflow.
- [ ] Solder high-current XT60 battery leads to 20A fuse holder and master kill switch.
- [ ] Calibrate Buck Converter 1 output to 5.1V DC (Logic) and Buck Converter 2 to 5.0V DC (Actuators).
- [ ] Connect common star-ground terminal tying LiPo GND, Buck 1 GND, Buck 2 GND, and controller grounds.
- [ ] Assemble 3D-printed rack-and-pinion mechanism; attach 2x MG995R metal gear servos and capacitive soil probe.
- [ ] Plumb the dual 5V pumps, 2-channel relay, tubing, and both fluid tanks (Water + Fertilizer).
- [ ] Mount water tank, submerge 5V pump, install one-way check valve, and route silicone line to root target zone.
- [ ] Neatly route all wiring harnesses with spiral wrap, zip ties, and label all connector headers.
