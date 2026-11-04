from gpiozero import PWMOutputDevice, DigitalOutputDevice
from time import sleep

# --- Hardware Mapping for BTS7960 Motor Drivers (6WD Skid-Steer) ---
left_en = DigitalOutputDevice(5)   # L_EN and R_EN tied to GPIO 5
left_forward = PWMOutputDevice(6)  # RPWM
left_reverse = PWMOutputDevice(13) # LPWM

right_en = DigitalOutputDevice(19)  # L_EN and R_EN tied to GPIO 19
right_forward = PWMOutputDevice(26) # RPWM
right_reverse = PWMOutputDevice(21) # LPWM

# --- Hardware Mapping for Fertigation Pumps (Dual Relay) ---
# NOTE: Many 5V relays are active-low. If your pump turns on when the Pi boots, 
# change active_high=False.
water_pump = DigitalOutputDevice(17, active_high=True)
fert_pump = DigitalOutputDevice(27, active_high=True)

# --- Kinematics Functions ---
def enable_drivers():
    left_en.on()
    right_en.on()

def stop_motors():
    left_forward.value = 0
    left_reverse.value = 0
    right_forward.value = 0
    right_reverse.value = 0

def drive_forward(speed=0.5):
    stop_motors()
    left_forward.value = speed
    right_forward.value = speed

def pivot_right(speed=0.5):
    """Tank steer right"""
    stop_motors()
    left_forward.value = speed
    right_reverse.value = speed

# --- Fertigation Functions ---
def micro_dose(water_time, fert_time):
    """Dispense specific ratios of water and fertilizer"""
    print(f"Dispensing Fertilizer for {fert_time}s...")
    fert_pump.on()
    sleep(fert_time)
    fert_pump.off()
    
    print(f"Dispensing Water for {water_time}s...")
    water_pump.on()
    sleep(water_time)
    water_pump.off()
    print("Dosing complete.")

if __name__ == '__main__':
    print("Initializing PrecisionRover Orchestrator...")
    enable_drivers()
    water_pump.off()
    fert_pump.off()
    
    try:
        # Hackathon Demo Sequence
        print("Moving to plant...")
        drive_forward(0.4)
        sleep(2)
        stop_motors()
        
        print("Target Reached. Commencing Micro-Dosing (3s Water, 1s Fertilizer)...")
        micro_dose(water_time=3, fert_time=1)
        
    except KeyboardInterrupt:
        print("Manual Override. Shutting down system.")
        stop_motors()
        water_pump.off()
        fert_pump.off()
