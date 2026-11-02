#!/usr/bin/env python3
"""
PrecisionRover - Main Orchestrator Loop
Platform: Raspberry Pi 5
Hackathon: CHIP TO CROP 2.0
Role: Dev 1 Space (Core Orchestrator)
"""

import time
import json
import threading
import queue
import serial
from gpiozero import DigitalOutputDevice
from adafruit_pca9685 import PCA9685
import board
import busio
import paho.mqtt.client as mqtt

# ======================== PIN DEFINITIONS ========================
# L298N Motor Driver A (Left Front & Left Rear)
PIN_LF_EN  = 12   # Hardware PWM
PIN_LF_IN1 = 5
PIN_LF_IN2 = 6
PIN_LR_EN  = 13   # Hardware PWM
PIN_LR_IN3 = 19
PIN_LR_IN4 = 26

# L298N Motor Driver B (Right Front & Right Rear)
PIN_RF_EN  = 18   # Hardware PWM
PIN_RF_IN1 = 23
PIN_RF_IN2 = 24
PIN_RR_EN  = 16   # Hardware PWM
PIN_RR_IN3 = 20
PIN_RR_IN4 = 21

PIN_RELAY_PUMP  = 4
ULTRASONIC_TRIG = 27
ULTRASONIC_ECHO = 22

# ==================== CONSTANTS & PROTOCOLS =====================
SERIAL_PORT_ESP32 = "/dev/ttyUSB0"
SERIAL_PORT_MAIX  = "/dev/ttyAMA0"
BAUD_RATE         = 115200

MQTT_BROKER          = "localhost"
MQTT_TOPIC_TELEMETRY = "precisionrover/telemetry"

# Thread-safe Communication Queues
vision_queue = queue.Queue(maxsize=10)
sensor_queue = queue.Queue(maxsize=10)


# ======================== ACTUATOR DRIVER ========================
class MotorController:
    """Mecanum kinematics controller using dual L298N H-bridges."""
    def __init__(self):
        self.lf_in1 = DigitalOutputDevice(PIN_LF_IN1)
        self.lf_in2 = DigitalOutputDevice(PIN_LF_IN2)
        self.lr_in3 = DigitalOutputDevice(PIN_LR_IN3)
        self.lr_in4 = DigitalOutputDevice(PIN_LR_IN4)
        
        self.rf_in1 = DigitalOutputDevice(PIN_RF_IN1)
        self.rf_in2 = DigitalOutputDevice(PIN_RF_IN2)
        self.rr_in3 = DigitalOutputDevice(PIN_RR_IN3)
        self.rr_in4 = DigitalOutputDevice(PIN_RR_IN4)

    def stop(self):
        for dev in [self.lf_in1, self.lf_in2, self.lr_in3, self.lr_in4,
                    self.rf_in1, self.rf_in2, self.rr_in3, self.rr_in4]:
            dev.off()

    def strafe_left(self):
        # FL reverse, FR forward, RL forward, RR reverse
        self.lf_in1.off(); self.lf_in2.on()
        self.rf_in1.on();  self.rf_in2.off()
        self.lr_in3.on();  self.lr_in4.off()
        self.rr_in3.off(); self.rr_in4.on()

    def strafe_right(self):
        # FL forward, FR reverse, RL reverse, RR forward
        self.lf_in1.on();  self.lf_in2.off()
        self.rf_in1.off(); self.rf_in2.on()
        self.lr_in3.off(); self.lr_in4.on()
        self.rr_in3.on();  self.rr_in4.off()

    def forward(self):
        self.lf_in1.on(); self.lf_in2.off()
        self.rf_in1.on(); self.rf_in2.off()
        self.lr_in3.on(); self.lr_in4.off()
        self.rr_in3.on(); self.rr_in4.off()


# ========================= SERIAL LISTENERS ======================
def read_esp32_serial(port):
    """Continuously parse incoming JSON telemetry from ESP32."""
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
        print(f"[ERR] ESP32 Serial error: {e}")


def read_maixcam_uart(port):
    """Continuously parse single-line control strings from MaixCam."""
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
        while True:
            cmd = ser.readline().decode('utf-8', errors='ignore').strip()
            if cmd in ["STRAFE_LEFT", "STRAFE_RIGHT", "ALIGNED_STOP", "NO_TARGET"]:
                if not vision_queue.full():
                    vision_queue.put(cmd)
    except Exception as e:
        print(f"[ERR] MaixCam UART error: {e}")


# ========================== MAIN ROUTINE =========================
def main():
    print("[INIT] Starting PrecisionRover Main Orchestrator...")
    motors = MotorController()
    pump_relay = DigitalOutputDevice(PIN_RELAY_PUMP, active_high=False, initial_value=False)
    
    # Initialize PCA9685 via CircuitPython Board Bus
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c)
        pca.frequency = 50
    except Exception as e:
        pca = None
        print(f"[WARN] PCA9685 not initialized: {e}")

    # Launch Serial Ingestion Threads
    t_esp = threading.Thread(target=read_esp32_serial, args=(SERIAL_PORT_ESP32,), daemon=True)
    t_maix = threading.Thread(target=read_maixcam_uart, args=(SERIAL_PORT_MAIX,), daemon=True)
    t_esp.start()
    t_maix.start()

    # MQTT Client Setup
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "Pi5_Orchestrator")
    try:
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[WARN] MQTT Broker unreachable: {e}")

    state = "SEARCHING"
    latest_sensor_data = {}

    try:
        while True:
            # Drain sensor queue for latest payload
            while not sensor_queue.empty():
                latest_sensor_data = sensor_queue.get_nowait()

            # State Machine Evaluation
            if state == "SEARCHING":
                vision_cmd = vision_queue.get() if not vision_queue.empty() else "NO_TARGET"
                
                if vision_cmd == "STRAFE_LEFT":
                    motors.strafe_left()
                elif vision_cmd == "STRAFE_RIGHT":
                    motors.strafe_right()
                elif vision_cmd == "ALIGNED_STOP":
                    motors.stop()
                    print("[FSM] Plant aligned. Transitioning to PROBING.")
                    state = "PROBING"
                else:
                    motors.forward()

            elif state == "PROBING":
                motors.stop()
                # Deploy Servo Arm
                if pca:
                    pca.channels[0].duty_cycle = 0x1A00  # Set deployment angle (~90 deg)
                    time.sleep(2.0)                      # Soil insertion delay
                
                # Check soil moisture from telemetry
                moisture = latest_sensor_data.get("soil_moisture_pct", 100.0)
                print(f"[DATA] In-situ Soil Moisture: {moisture}%")

                if moisture < 30.0:
                    print("[ACTION] Low moisture detected. Triggering Irrigation...")
                    state = "IRRIGATING"
                else:
                    print("[ACTION] Moisture adequate. Retracting probe.")
                    state = "RETRACTING"

            elif state == "IRRIGATING":
                pump_relay.on()
                time.sleep(3.0)  # Dispense water pulse
                pump_relay.off()
                state = "RETRACTING"

            elif state == "RETRACTING":
                if pca:
                    pca.channels[0].duty_cycle = 0x0D00  # Retract to 0 deg
                    time.sleep(1.5)
                state = "SEARCHING"

            # Periodic Telemetry Publish
            telemetry_packet = {
                "timestamp": time.time(),
                "fsm_state": state,
                "sensors": latest_sensor_data
            }
            mqtt_client.publish(MQTT_TOPIC_TELEMETRY, json.dumps(telemetry_packet))
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("[SHUTDOWN] Stopping all rover actuators...")
        motors.stop()
        pump_relay.off()
        if pca:
            pca.deinit()


if __name__ == "__main__":
    main()
