#!/usr/bin/env python3
"""
PrecisionRover - 6WD Skid-Steer Main Orchestrator Loop
Platform: Raspberry Pi 5
Hackathon: CHIP TO CROP 2.0
Role: Dev 1 Space (Core Orchestrator)

Kinematics: 6WD Skid-Steer (Tank Drive) via Dual BTS7960 43A High-Current H-Bridges
Sensors & Actuators:
  - 2x BTS7960 Motor Drivers (3 Left DC Motors, 3 Right DC Motors)
  - PCA9685 16-Channel PWM Servo Driver (2x MG995R Servos)
  - 5V Submersible Pump Relay
  - HC-SR04 Ultrasonic Distance Sensor
  - MaixCam UART & ESP32 USB Serial Ingestion
  - MQTT Telemetry Publisher
"""

import time
import json
import threading
import queue
import serial
from gpiozero import PWMOutputDevice, DigitalOutputDevice, DistanceSensor
from adafruit_pca9685 import PCA9685
import board
import busio
import paho.mqtt.client as mqtt

# ======================== PIN DEFINITIONS ========================
# BTS7960 Motor Driver 1: Left Bank (3x DC Motors in parallel)
PIN_L_RPWM = 12   # Forward PWM (Hardware PWM0)
PIN_L_LPWM = 13   # Reverse PWM (Hardware PWM1)
PIN_L_REN  = 5    # Right Enable (Active High)
PIN_L_LEN  = 6    # Left Enable (Active High)

# BTS7960 Motor Driver 2: Right Bank (3x DC Motors in parallel)
PIN_R_RPWM = 18   # Forward PWM (Hardware PWM0)
PIN_R_LPWM = 19   # Reverse PWM (Hardware PWM1)
PIN_R_REN  = 23   # Right Enable (Active High)
PIN_R_LEN  = 24   # Left Enable (Active High)

# Actuation & Sensor Pins
PIN_RELAY_PUMP  = 4
ULTRASONIC_TRIG = 27
ULTRASONIC_ECHO = 22

# Serial & Network Protocol Definitions
SERIAL_PORT_ESP32 = "/dev/ttyUSB0"
SERIAL_PORT_MAIX  = "/dev/ttyAMA0"
BAUD_RATE         = 115200

MQTT_BROKER          = "localhost"
MQTT_TOPIC_TELEMETRY = "precisionrover/telemetry"

# Thread-safe Communication Queues
vision_queue = queue.Queue(maxsize=10)
sensor_queue = queue.Queue(maxsize=10)


# ==================== 6WD SKID-STEER DRIVER =====================
class BTS7960Bank:
    """Controls one side of 3x DC motors driven by a BTS7960 H-Bridge."""
    def __init__(self, rpwm_pin, lpwm_pin, ren_pin, len_pin, frequency=1000):
        self.rpwm = PWMOutputDevice(rpwm_pin, frequency=frequency, initial_value=0)
        self.lpwm = PWMOutputDevice(lpwm_pin, frequency=frequency, initial_value=0)
        self.ren  = DigitalOutputDevice(ren_pin, initial_value=True)
        self.len  = DigitalOutputDevice(len_pin, initial_value=True)

    def drive(self, speed):
        """
        Drive bank with normalized speed in [-1.0, 1.0].
        Positive: Forward (RPWM active, LPWM 0)
        Negative: Reverse (LPWM active, RPWM 0)
        0.0: Stop
        """
        self.ren.on()
        self.len.on()
        speed = max(-1.0, min(1.0, speed))
        if speed > 0:
            self.lpwm.value = 0.0
            self.rpwm.value = speed
        elif speed < 0:
            self.rpwm.value = 0.0
            self.lpwm.value = abs(speed)
        else:
            self.stop()

    def stop(self):
        self.rpwm.value = 0.0
        self.lpwm.value = 0.0


class SkidSteer6WDController:
    """6WD Skid-Steer (Tank Drive) kinematics coordinator."""
    def __init__(self):
        self.left_bank  = BTS7960Bank(PIN_L_RPWM, PIN_L_LPWM, PIN_L_REN, PIN_L_LEN)
        self.right_bank = BTS7960Bank(PIN_R_RPWM, PIN_R_LPWM, PIN_R_REN, PIN_R_LEN)
        # Default cruise speeds and trim scalars
        self.base_speed = 0.6
        self.turn_speed = 0.55
        self.trim_left  = 1.0
        self.trim_right = 1.0

    def stop(self):
        self.left_bank.stop()
        self.right_bank.stop()

    def forward(self, speed=None):
        spd = (speed or self.base_speed)
        self.left_bank.drive(spd * self.trim_left)
        self.right_bank.drive(spd * self.trim_right)

    def reverse(self, speed=None):
        spd = (speed or self.base_speed)
        self.left_bank.drive(-spd * self.trim_left)
        self.right_bank.drive(-spd * self.trim_right)

    def steer_left(self, speed=None):
        """Skid turn left: left wheels reverse, right wheels forward."""
        spd = (speed or self.turn_speed)
        self.left_bank.drive(-spd * 0.7)
        self.right_bank.drive(spd)

    def steer_right(self, speed=None):
        """Skid turn right: left wheels forward, right wheels reverse."""
        spd = (speed or self.turn_speed)
        self.left_bank.drive(spd)
        self.right_bank.drive(-spd * 0.7)


# ===================== DUAL SERVO CONTROLLER ====================
class ProbeMechanism:
    """Controls vertical rack-and-pinion and deployment via PCA9685."""
    CHANNEL_RACK_PINION = 0  # Servo 1: Vertical insertion
    CHANNEL_DEPLOYMENT  = 1  # Servo 2: Angle articulation

    def __init__(self, pca_driver):
        self.pca = pca_driver

    def _set_angle(self, channel, angle):
        if not self.pca:
            return
        # MG995R 50Hz PWM: ~1.0ms (0 deg) to ~2.0ms (180 deg) -> ~5% to ~10% duty cycle
        min_duty = 0x0A00  # ~1.0ms (~65535 * 0.05)
        max_duty = 0x1E00  # ~2.0ms (~65535 * 0.10)
        duty = int(min_duty + (angle / 180.0) * (max_duty - min_duty))
        self.pca.channels[channel].duty_cycle = max(min_duty, min(max_duty, duty))

    def retract(self):
        print("[ARM] Retracting probe mechanism to home position...")
        self._set_angle(self.CHANNEL_DEPLOYMENT, 0)
        time.sleep(0.5)
        self._set_angle(self.CHANNEL_RACK_PINION, 0)

    def plunge(self):
        print("[ARM] Deploying probe and plunging into soil...")
        self._set_angle(self.CHANNEL_DEPLOYMENT, 90)
        time.sleep(0.5)
        self._set_angle(self.CHANNEL_RACK_PINION, 120)


# ========================= SERIAL LISTENERS ======================
def read_esp32_serial(port):
    """Continuously parse incoming single-line JSON telemetry from ESP32."""
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1.0)
        while True:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    payload = json.loads(line)
                    if not sensor_queue.full():
                        sensor_queue.put(payload)
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"[ERR] ESP32 Serial thread exception: {e}")


def read_maixcam_uart(port):
    """Continuously parse incoming ASCII steering strings from MaixCam."""
    allowed_cmds = {"STEER_LEFT", "STEER_RIGHT", "ALIGNED_STOP", "NO_TARGET", "STRAFE_LEFT", "STRAFE_RIGHT"}
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
        while True:
            cmd = ser.readline().decode('utf-8', errors='ignore').strip()
            if cmd in allowed_cmds:
                # Normalize legacy STRAFE to STEER
                if cmd == "STRAFE_LEFT":
                    cmd = "STEER_LEFT"
                elif cmd == "STRAFE_RIGHT":
                    cmd = "STEER_RIGHT"
                if not vision_queue.full():
                    vision_queue.put(cmd)
    except Exception as e:
        print(f"[ERR] MaixCam UART thread exception: {e}")


# ========================== MAIN ROUTINE =========================
def main():
    print("[INIT] Starting PrecisionRover 6WD Skid-Steer Orchestrator...")
    motors = SkidSteer6WDController()
    pump_relay = DigitalOutputDevice(PIN_RELAY_PUMP, active_high=False, initial_value=False)
    
    # Initialize Ultrasonic Obstacle Sensor
    try:
        sonar = DistanceSensor(echo=ULTRASONIC_ECHO, trigger=ULTRASONIC_TRIG, max_distance=2.0)
    except Exception as e:
        sonar = None
        print(f"[WARN] HC-SR04 sonar sensor unavailable: {e}")

    # Initialize PCA9685 via CircuitPython Board Bus
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c)
        pca.frequency = 50
    except Exception as e:
        pca = None
        print(f"[WARN] PCA9685 servo driver unavailable: {e}")

    probe = ProbeMechanism(pca)

    # Launch Background Sensor Ingestion Threads
    threading.Thread(target=read_esp32_serial, args=(SERIAL_PORT_ESP32,), daemon=True).start()
    threading.Thread(target=read_maixcam_uart, args=(SERIAL_PORT_MAIX,), daemon=True).start()

    # MQTT Client Setup
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "Pi5_6WD_Orchestrator")
    try:
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[WARN] MQTT Broker unreachable: {e}")

    state = "SEARCHING"
    latest_sensor_data = {}

    try:
        while True:
            # Drain sensor queue for latest payload from ESP32-S3
            while not sensor_queue.empty():
                latest_sensor_data = sensor_queue.get_nowait()

            # Obstacle Safety Check (read from ESP32-S3 sensor hub or fallback to local sonar)
            obstacle_dist_cm = latest_sensor_data.get("distance_cm", (sonar.distance * 100.0) if sonar else 100.0)
            if obstacle_dist_cm < 18.0 and state == "SEARCHING":
                print(f"[SAFETY] Obstacle detected at {obstacle_dist_cm:.1f} cm! Halting rover.")
                motors.stop()
                time.sleep(0.2)
                continue

            # State Machine Evaluation
            if state == "SEARCHING":
                vision_cmd = vision_queue.get() if not vision_queue.empty() else "NO_TARGET"
                
                if vision_cmd == "STEER_LEFT":
                    motors.steer_left()
                elif vision_cmd == "STEER_RIGHT":
                    motors.steer_right()
                elif vision_cmd == "ALIGNED_STOP":
                    motors.stop()
                    print("[FSM] Plant aligned. Transitioning to PROBING.")
                    state = "PROBING"
                else:
                    motors.forward()

            elif state == "PROBING":
                motors.stop()
                probe.plunge()
                time.sleep(2.0)  # Stabilize sensor in root zone
                
                # Check soil moisture from ESP32 telemetry
                moisture = latest_sensor_data.get("soil_moisture_pct", 100.0)
                print(f"[DATA] In-situ Soil Moisture: {moisture}%")

                if moisture < 35.0:
                    print("[ACTION] Low moisture detected. Triggering Irrigation...")
                    state = "IRRIGATING"
                else:
                    print("[ACTION] Moisture adequate. Retracting probe.")
                    state = "RETRACTING"

            elif state == "IRRIGATING":
                pump_relay.on()
                time.sleep(3.0)  # Deliver 5V pump pulse
                pump_relay.off()
                state = "RETRACTING"

            elif state == "RETRACTING":
                probe.retract()
                time.sleep(1.5)
                state = "SEARCHING"

            # Periodic Unified Telemetry Dispatch
            telemetry_packet = {
                "timestamp": time.time(),
                "fsm_state": state,
                "obstacle_dist_cm": round(obstacle_dist_cm, 1),
                "sensors": latest_sensor_data
            }
            mqtt_client.publish(MQTT_TOPIC_TELEMETRY, json.dumps(telemetry_packet))
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("[SHUTDOWN] Halting rover actuators...")
        motors.stop()
        pump_relay.off()
        if pca:
            probe.retract()
            pca.deinit()


if __name__ == "__main__":
    main()
