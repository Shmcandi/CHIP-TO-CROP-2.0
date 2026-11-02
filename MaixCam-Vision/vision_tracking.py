"""
PrecisionRover - Edge AI Visual Crop Alignment
Platform: Sipeed MaixCam (K230 / MaixPy v4)
Hackathon: CHIP TO CROP 2.0
Role: Dev 2 Space (Vision AI)
"""

from maix import camera, display, image, uart
import time

# ======================= CONFIGURATION ==========================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

DEADBAND_LEFT = 260
DEADBAND_RIGHT = 380

UART_PORT = "/dev/ttyS0"  # MaixCam hardware UART port
UART_BAUDRATE = 115200

# Color Thresholds for Healthy Foliage (LAB Color Space)
# (L_MIN, L_MAX, A_MIN, A_MAX, B_MIN, B_MAX)
PLANT_LAB_THRESHOLDS = [(30, 85, -64, -20, 10, 60)]


# ======================= INITIALIZATION =========================
def init_system():
    cam = camera.Camera(FRAME_WIDTH, FRAME_HEIGHT)
    disp = display.Display()
    serial_comm = uart.UART(UART_PORT, UART_BAUDRATE)
    return cam, disp, serial_comm


# ========================= VISION LOOP ==========================
def main():
    cam, disp, comm = init_system()
    last_command = ""
    command_hold_counter = 0

    print("[MAIXCAM] Vision Alignment Loop Active...")

    while True:
        img = cam.read()
        if img is None:
            continue

        # Extract Green Foliage Blobs
        blobs = img.find_blobs(PLANT_LAB_THRESHOLDS, pixels_threshold=500, area_threshold=800, merge=True)
        
        target_command = "NO_TARGET"

        if blobs:
            # Sort blobs by area to lock onto closest target
            largest_blob = max(blobs, key=lambda b: b.pixels())
            cx = largest_blob.cx()
            cy = largest_blob.cy()

            # Draw visual debug artifacts on the display frame
            img.draw_rectangle(largest_blob.rect(), color=(255, 0, 0), thickness=2)
            img.draw_cross(cx, cy, color=(0, 0, 255), size=10)

            # Spatial Alignment Logic
            if cx < DEADBAND_LEFT:
                target_command = "STRAFE_LEFT"
            elif cx > DEADBAND_RIGHT:
                target_command = "STRAFE_RIGHT"
            else:
                target_command = "ALIGNED_STOP"

        # Frame Guides
        img.draw_line(DEADBAND_LEFT, 0, DEADBAND_LEFT, FRAME_HEIGHT, color=(255, 255, 0), thickness=1)
        img.draw_line(DEADBAND_RIGHT, 0, DEADBAND_RIGHT, FRAME_HEIGHT, color=(255, 255, 0), thickness=1)

        # Transmission Logic with Hysteresis
        if target_command == last_command:
            command_hold_counter += 1
        else:
            command_hold_counter = 0
            last_command = target_command

        # Send command when stable for >= 3 frames
        if command_hold_counter >= 3:
            payload = f"{target_command}\n"
            comm.write(payload.encode('ascii'))
            command_hold_counter = 0  # Reset counter to throttle output

        # Render to MaixCam screen
        img.draw_string(10, 10, f"CMD: {last_command}", color=(0, 255, 0), scale=1.5)
        disp.show(img)


if __name__ == "__main__":
    main()
