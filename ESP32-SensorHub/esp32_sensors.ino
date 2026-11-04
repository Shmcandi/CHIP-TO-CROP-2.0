/**
 * PrecisionRover - ESP32-S3 Sensor Hub Firmware
 * Target: ESP32-S3 Dev Module (Arduino Core / C++)
 * Hackathon: CHIP TO CROP 2.0
 * Role: Dev 3 Space (Sensor Hub & Environment Acquisition)
 * 
 * Hardware Sensors:
 *  - HC-SR04 Ultrasonic Distance Sensor (Obstacle clearance)
 *  - Analog Capacitive Soil Moisture Sensor v1.2 (ADC1)
 *  - Analog Optical Turbidity Sensor (ADC1)
 * 
 * Stream: Single-line JSON over USB CDC Serial at 10 Hz:
 * {"distance_cm":42.5,"soil_moisture_pct":64.2,"turbidity_ntu":15.3,"turb_v":2.95}
 */

#include <Arduino.h>

// ======================== HARDWARE PINS (ESP32-S3) =========================
// ADC1 Channels (Safe to use alongside USB / Wi-Fi)
const int PIN_SOIL_ADC       = 1;  // ESP32-S3 GPIO 1 (ADC1_CH0)
const int PIN_TURBIDITY_ADC  = 2;  // ESP32-S3 GPIO 2 (ADC1_CH1)

// HC-SR04 Ultrasonic Sensor Pins
const int PIN_TRIG           = 4;  // GPIO 4
const int PIN_ECHO           = 5;  // GPIO 5

// ======================= CALIBRATION CONSTANTS =============================
// Capacitive Soil Moisture Raw Calibration (12-bit ADC: 0 - 4095)
const float SOIL_RAW_AIR     = 3150.0; // In dry air
const float SOIL_RAW_WATER   = 1420.0; // Submerged in water

// Turbidity Sensor Reference Constants
const float ADC_VOLTAGE_REF  = 3.3;
const float ADC_RESOLUTION   = 4095.0;

// Exponential Moving Average (EMA) Low-Pass Filter Alpha (0.0 to 1.0)
const float FILTER_ALPHA     = 0.15;

// Dispatch Rate (10 Hz = 100ms interval)
const unsigned long INTERVAL = 100;

// ======================= STATE VARIABLES ===================================
float filtered_soil_raw      = 2500.0;
float filtered_turb_raw      = 2000.0;
float filtered_distance_cm   = 100.0;
unsigned long last_transmit  = 0;

// Helper: Measure HC-SR04 Distance with Timeout (cm)
float read_ultrasonic_distance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  // 25ms timeout corresponds to ~4.3 meters max range
  unsigned long duration_us = pulseIn(PIN_ECHO, HIGH, 25000);
  if (duration_us == 0) {
    return -1.0; // Out of range or timeout
  }
  // Speed of sound: 343 m/s = 0.0343 cm/us (divide by 2 for round-trip)
  float dist_cm = (duration_us * 0.0343) / 2.0;
  return constrain(dist_cm, 2.0, 400.0);
}

void setup() {
  // Initialize USB CDC Serial (ESP32-S3 USB CDC enabled)
  Serial.begin(115200);

  // Configure Ultrasonic GPIOs
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);

  // Configure ESP32-S3 ADC Attenuation for full 0 - 3.3V range
  analogSetPinAttenuation(PIN_SOIL_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_TURBIDITY_ADC, ADC_11db);

  // Seed initial filter states
  filtered_soil_raw = analogRead(PIN_SOIL_ADC);
  filtered_turb_raw = analogRead(PIN_TURBIDITY_ADC);
}

void loop() {
  // 1. Read Raw Analog Sensors
  int raw_soil = analogRead(PIN_SOIL_ADC);
  int raw_turb = analogRead(PIN_TURBIDITY_ADC);

  // 2. Apply Exponential Moving Average (EMA) Low-Pass Filter
  filtered_soil_raw = (FILTER_ALPHA * raw_soil) + ((1.0 - FILTER_ALPHA) * filtered_soil_raw);
  filtered_turb_raw = (FILTER_ALPHA * raw_turb) + ((1.0 - FILTER_ALPHA) * filtered_turb_raw);

  // 3. Periodic Transmission at 10 Hz
  if (millis() - last_transmit >= INTERVAL) {
    last_transmit = millis();

    // Ultrasonic ping
    float dist = read_ultrasonic_distance();
    if (dist > 0.0) {
      filtered_distance_cm = (0.3 * dist) + (0.7 * filtered_distance_cm);
    }

    // Soil moisture percentage calculation (clamped 0 - 100%)
    float moisture_pct = ((SOIL_RAW_AIR - filtered_soil_raw) / (SOIL_RAW_AIR - SOIL_RAW_WATER)) * 100.0;
    moisture_pct = constrain(moisture_pct, 0.0, 100.0);

    // Turbidity voltage and NTU calculation
    float turb_voltage = (filtered_turb_raw / ADC_RESOLUTION) * ADC_VOLTAGE_REF;
    float ntu = -1120.4 * (turb_voltage * turb_voltage) + (5742.3 * turb_voltage) - 4353.8;
    ntu = constrain(ntu, 0.0, 3000.0);

    // Dispatch Structured JSON Line
    Serial.print("{\"distance_cm\":");
    Serial.print(filtered_distance_cm, 1);
    Serial.print(",\"soil_moisture_pct\":");
    Serial.print(moisture_pct, 1);
    Serial.print(",\"turbidity_ntu\":");
    Serial.print(ntu, 1);
    Serial.print(",\"turb_v\":");
    Serial.print(turb_voltage, 2);
    Serial.println("}");
  }
}
