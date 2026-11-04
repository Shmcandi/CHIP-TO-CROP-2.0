/**
 * PrecisionRover - Analog Sensor Hub Firmware (6WD Rover Architecture)
 * Target: ESP32 Dev Module (Arduino Core)
 * Hackathon: CHIP TO CROP 2.0
 * Role: Dev 3 Space (Sensor Hub)
 */

#include <Arduino.h>

// ======================== HARDWARE PINS =========================
const int PIN_SOIL_ADC       = 34; // ADC1_CH6 (Isolated from Wi-Fi ADC2 conflicts)
const int PIN_TURBIDITY_ADC  = 35; // ADC1_CH7

// ======================= CALIBRATION CONSTANTS ==================
// Capacitive Sensor Raw Calibration (12-bit ADC: 0 - 4095)
const float SOIL_RAW_AIR     = 3200.0; // Sensor completely dry in air
const float SOIL_RAW_WATER   = 1450.0; // Sensor submerged in water to max line

// Turbidity Sensor Parameters
const float ADC_VOLTAGE_REF  = 3.3;
const float ADC_RESOLUTION   = 4095.0;

// Low-pass Filter Constant (0.0 to 1.0) - Lower = heavier smoothing
const float FILTER_ALPHA     = 0.15;

// State Variables
float filtered_soil_raw      = 2500.0;
float filtered_turb_raw      = 2000.0;
unsigned long last_transmit  = 0;
const unsigned long INTERVAL = 100; // 10 Hz transmission rate (100ms)

void setup() {
  Serial.begin(115200);
  
  // Set ADC Attenuation to measure full 0 - 3.3V range
  analogSetPinAttenuation(PIN_SOIL_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_TURBIDITY_ADC, ADC_11db);

  // Seed initial filter values
  filtered_soil_raw = analogRead(PIN_SOIL_ADC);
  filtered_turb_raw = analogRead(PIN_TURBIDITY_ADC);
}

void loop() {
  // Read Raw Analog Values
  int raw_soil = analogRead(PIN_SOIL_ADC);
  int raw_turb = analogRead(PIN_TURBIDITY_ADC);

  // Apply Exponential Moving Average (EMA) to suppress motor electrical ripple
  filtered_soil_raw = (FILTER_ALPHA * raw_soil) + ((1.0 - FILTER_ALPHA) * filtered_soil_raw);
  filtered_turb_raw = (FILTER_ALPHA * raw_turb) + ((1.0 - FILTER_ALPHA) * filtered_turb_raw);

  // Dispatch at deterministic 10Hz intervals
  if (millis() - last_transmit >= INTERVAL) {
    last_transmit = millis();

    // Calculate percentage (clamped between 0.0% and 100.0%)
    float moisture_pct = ((SOIL_RAW_AIR - filtered_soil_raw) / (SOIL_RAW_AIR - SOIL_RAW_WATER)) * 100.0;
    moisture_pct = constrain(moisture_pct, 0.0, 100.0);

    // Calculate Turbidity Sensor Output Voltage
    float turb_voltage = (filtered_turb_raw / ADC_RESOLUTION) * ADC_VOLTAGE_REF;
    
    // Polynomial approximation for NTU (Nephelometric Turbidity Units)
    float ntu = -1120.4 * (turb_voltage * turb_voltage) + (5742.3 * turb_voltage) - 4353.8;
    ntu = constrain(ntu, 0.0, 3000.0);

    // Stream Single-Line JSON Telemetry Payload
    Serial.print("{\"soil_moisture_pct\":");
    Serial.print(moisture_pct, 2);
    Serial.print(",\"turbidity_ntu\":");
    Serial.print(ntu, 1);
    Serial.print(",\"turb_v\":");
    Serial.print(turb_voltage, 2);
    Serial.println("}");
  }
}
