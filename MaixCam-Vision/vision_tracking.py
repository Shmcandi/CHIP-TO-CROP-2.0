"""
PrecisionRover - Edge AI Visual Crop Alignment (6WD Skid-Steer Edition)
Platform: Sipeed MaixCam (K230 / MaixPy v4)
Hackathon: CHIP TO CROP 2.0
Role: Dev 2 Space (Vision AI)

Output Commands over UART:
  - STEER_LEFT   : Target plant located in left sector
  - ALIGNED_STOP : Target plant centered within deadband
  - STEER_RIGHT  : Target plant located in right sector
  - NO_TARGET    : No crop detected in frame
"""

import argparse
import sys
import time

# ======================= CONFIGURATION ==========================
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

DEADBAND_LEFT = 260
DEADBAND_RIGHT = 380

UART_PORT = "/dev/ttyS0"  # MaixCam hardware UART port
UART_BAUDRATE = 115200

# Color Thresholds for Foliage in LAB Color Space
# (L_MIN, L_MAX, A_MIN, A_MAX, B_MIN, B_MAX)
PLANT_LAB_THRESHOLDS = [(30, 85, -64, -20, 10, 60)]


# ======================= INITIALIZATION =========================
def init_system():
    from maix import camera, display, uart

    cam = camera.Camera(FRAME_WIDTH, FRAME_HEIGHT)
    disp = display.Display()
    serial_comm = uart.UART(UART_PORT, UART_BAUDRATE)
    return cam, disp, serial_comm


def run_simulator():
    """Mock ASCII stream for testing orchestrator pipelines."""
    commands = [
        "STEER_LEFT",
        "STEER_LEFT",
        "ALIGNED_STOP",
        "ALIGNED_STOP",
        "STEER_RIGHT",
        "STEER_RIGHT",
        "NO_TARGET",
        "NO_TARGET",
        "ALIGNED_STOP",
        "ALIGNED_STOP",
    ]
    for index, command in enumerate(commands):
        print(command, flush=True)
        if index < len(commands) - 1:
            time.sleep(0.1)


def run_desktop_simulator():
    """Interactive GUI simulator for desktop validation."""
    import math
    import cv2
    import numpy as np

    plant_x = FRAME_WIDTH // 2
    plant_visible = True
    stressed = False
    auto_move = False
    command = "NO_TARGET"
    candidate = command
    stable_frames = 0
    started = time.monotonic()

    while True:
        now = time.monotonic()
        if auto_move:
            plant_x = int(FRAME_WIDTH / 2 + math.sin(now - started) * 210)

        frame = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), (38, 49, 39), dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (FRAME_WIDTH - 1, FRAME_HEIGHT - 1), (76, 91, 73), 3)
        for y in range(95, FRAME_HEIGHT, 70):
            cv2.line(frame, (0, y), (FRAME_WIDTH, y), (49, 65, 53), 1)

        # Draw alignment deadband lines
        cv2.rectangle(frame, (DEADBAND_LEFT, 0), (DEADBAND_RIGHT, FRAME_HEIGHT), (55, 63, 45), -1)
        cv2.line(frame, (DEADBAND_LEFT, 0), (DEADBAND_LEFT, FRAME_HEIGHT), (0, 220, 255), 2)
        cv2.line(frame, (DEADBAND_RIGHT, 0), (DEADBAND_RIGHT, FRAME_HEIGHT), (0, 220, 255), 2)

        if plant_visible:
            leaf_color = (65, 180, 65) if not stressed else (35, 185, 210)
            cv2.line(frame, (plant_x, 345), (plant_x, 215), (55, 135, 65), 10)
            for dx, dy, angle in [(-38, -15, 25), (35, -40, -25), (-42, -75, 20), (37, -105, -20), (0, -135, 0)]:
                center = (plant_x + dx, 345 + dy)
                cv2.ellipse(frame, center, (42, 17), angle, 0, 360, leaf_color, -1)
                cv2.ellipse(frame, center, (42, 17), angle, 0, 360, (125, 210, 125), 1)
            cv2.rectangle(frame, (plant_x - 75, 190), (plant_x + 75, 365), (245, 245, 245), 1)
            
            # Skid-Steer Alignment Logic
            if plant_x < DEADBAND_LEFT:
                next_candidate = "STEER_LEFT"
            elif plant_x > DEADBAND_RIGHT:
                next_candidate = "STEER_RIGHT"
            else:
                next_candidate = "ALIGNED_STOP"
        else:
            next_candidate = "NO_TARGET"

        if next_candidate == candidate:
            stable_frames += 1
        else:
            candidate = next_candidate
            stable_frames = 1
        if stable_frames >= 3:
            command = candidate

        cv2.putText(frame, f"6WD VISION SIMULATOR  |  {command}", (18, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (245, 245, 245), 2)
        cv2.putText(frame, f"Plant: {'STRESSED' if stressed else 'HEALTHY'}   Target: {'VISIBLE' if plant_visible else 'HIDDEN'}", (18, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (225, 225, 225), 1)
        cv2.imshow("CHIP TO CROP - 6WD Skid-Steer Tracking Simulator", frame)

        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            stressed = not stressed
        elif key == ord("p"):
            plant_visible = not plant_visible
        elif key == ord("a"):
            auto_move = False
            plant_x = max(30, plant_x - 50)
        elif key == ord("d"):
            auto_move = False
            plant_x = min(FRAME_WIDTH - 30, plant_x + 50)
        elif key == ord("c"):
            auto_move = False
            plant_x = FRAME_WIDTH // 2
        elif key == ord("m"):
            auto_move = not auto_move
            started = time.monotonic()

    cv2.destroyAllWindows()


# ========================= VISION LOOP ==========================
def main():
    cam, disp, comm = init_system()
    last_command = ""
    command_hold_counter = 0

    print("[MAIXCAM] 6WD Vision Alignment Loop Active...")

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

            # Visual debug artifacts on display frame
            img.draw_rectangle(largest_blob.rect(), color=(255, 0, 0), thickness=2)
            img.draw_cross(cx, cy, color=(0, 0, 255), size=10)

            # Spatial Skid-Steer Alignment Logic
            if cx < DEADBAND_LEFT:
                target_command = "STEER_LEFT"
            elif cx > DEADBAND_RIGHT:
                target_command = "STEER_RIGHT"
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
            command_hold_counter = 0

        # Render to MaixCam screen
        img.draw_string(10, 10, f"CMD: {last_command}", color=(0, 255, 0), scale=1.5)
        disp.show(img)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--simulator", action="store_true")
    parser.add_argument("--port", default=UART_PORT)
    args = parser.parse_args()

    if args.simulator:
        run_desktop_simulator()
    elif args.no_gui:
        if args.port != "stdout":
            print("Headless simulation requires --port stdout", file=sys.stderr)
            sys.exit(2)
        run_simulator()
    else:
        main()
