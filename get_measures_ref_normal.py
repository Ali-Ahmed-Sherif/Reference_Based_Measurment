import cv2
import math
import os
from pathlib import Path
from tkinter import Tk, filedialog

# Global variables
clicked_points = []
reference_scales = []
reference_points = []  # Store all reference point pairs
mode = "reference"
average_scale = None
measured_lines = []

display_width = 1080
resize_ratio = 1.0
original_frame = None

# Zoom variables
zoom_factor = 1.0
zoom_center_x = 0.5
zoom_center_y = 0.5

# Image navigation
image_paths = []
current_image_index = 0
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


# ---------------- Helper Functions ----------------
def euclidean_distance(p1, p2):
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def reset_zoom():
    global zoom_factor, zoom_center_x, zoom_center_y
    zoom_factor = 1.0
    zoom_center_x = 0.5
    zoom_center_y = 0.5

def reset_measurements():
    global clicked_points, reference_scales, reference_points, average_scale, measured_lines, mode
    clicked_points = []
    reference_scales = []
    reference_points = []
    average_scale = None
    measured_lines = []
    mode = "reference"

def recompute_average_scale():
    global average_scale, reference_scales
    if reference_scales:
        average_scale = sum(reference_scales) / len(reference_scales)
    else:
        average_scale = None

def undo_last():
    """
    Context-aware undo using key 'c':
    1) If there is an unfinished click pair, remove the last clicked point first.
    2) In reference mode, remove the last reference pair and its scale.
    3) In target mode, remove the last measured target line.
    """
    global clicked_points, reference_scales, reference_points, average_scale, measured_lines, mode

    # Remove unfinished current click first
    if clicked_points:
        removed = clicked_points.pop()
        print(f"Removed pending clicked point: {removed}")
        return

    if mode == "reference":
        if reference_points:
            removed_ref = reference_points.pop()
            removed_scale = reference_scales.pop()
            recompute_average_scale()
            print(f"Removed last reference pair: {removed_ref}")
            print(f"Removed its scale: {removed_scale:.6f}")
            if average_scale is not None:
                print(f"Updated average scale: {average_scale:.6f}")
            else:
                print("No references left. Average scale cleared.")
        else:
            print("No reference pairs to remove.")

    elif mode == "target":
        if measured_lines:
            removed_line = measured_lines.pop()
            print(f"Removed last measured line: {removed_line[0]} -> {removed_line[1]}")
        else:
            print("No measured target lines to remove.")

def load_image_by_index(index, keep_measurements=False):
    global original_frame, resize_ratio, current_image_index
    global clicked_points, reference_scales, reference_points, average_scale, measured_lines

    if not image_paths:
        return False

    if index < 0 or index >= len(image_paths):
        return False

    image_path = image_paths[index]
    frame = cv2.imread(str(image_path))

    if frame is None:
        print(f"Could not load image: {image_path}")
        return False

    original_frame = frame
    current_image_index = index

    h, w = original_frame.shape[:2]
    resize_ratio = display_width / w

    reset_zoom()

    if not keep_measurements:
        reset_measurements()

    print(f"\nLoaded [{current_image_index + 1}/{len(image_paths)}]: {image_path.name}")
    return True

def get_images_in_folder(selected_path):
    folder = selected_path.parent
    files = sorted(
        [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda p: p.name.lower()
    )
    return files

def screen_to_image_coords(screen_x, screen_y, img_width, img_height):
    global zoom_factor, zoom_center_x, zoom_center_y, resize_ratio, display_width

    visible_width = 1.0 / zoom_factor
    visible_height = 1.0 / zoom_factor

    left = zoom_center_x - visible_width / 2
    top = zoom_center_y - visible_height / 2

    left = max(0, min(1 - visible_width, left))
    top = max(0, min(1 - visible_height, top))

    norm_x = screen_x / display_width
    norm_y = screen_y / (img_height * resize_ratio)

    img_x = int((left + norm_x * visible_width) * img_width)
    img_y = int((top + norm_y * visible_height) * img_height)

    return img_x, img_y

def image_to_screen_coords(img_x, img_y, img_width, img_height):
    global zoom_factor, zoom_center_x, zoom_center_y, resize_ratio, display_width

    visible_width = 1.0 / zoom_factor
    visible_height = 1.0 / zoom_factor

    left = zoom_center_x - visible_width / 2
    top = zoom_center_y - visible_height / 2

    left = max(0, min(1 - visible_width, left))
    top = max(0, min(1 - visible_height, top))

    norm_x = img_x / img_width
    norm_y = img_y / img_height

    screen_x = int((norm_x - left) / visible_width * display_width)
    screen_y = int((norm_y - top) / visible_height * (img_height * resize_ratio))

    return screen_x, screen_y

def mouse_callback(event, x, y, flags, param):
    global clicked_points, reference_scales, reference_points, average_scale, measured_lines
    global mode, zoom_factor, zoom_center_x, zoom_center_y
    global original_frame, resize_ratio

    if original_frame is None:
        return

    h, w = original_frame.shape[:2]

    # Mouse wheel zoom
    if event == cv2.EVENT_MOUSEWHEEL:
        mouse_norm_x = x / display_width
        mouse_norm_y = y / (h * resize_ratio)

        if flags > 0:
            new_zoom = min(zoom_factor + 0.5, 10.0)
        else:
            new_zoom = max(zoom_factor - 0.5, 1.0)

        if new_zoom != zoom_factor:
            visible_width_old = 1.0 / zoom_factor
            visible_height_old = 1.0 / zoom_factor
            left_old = max(0, min(1 - visible_width_old, zoom_center_x - visible_width_old / 2))
            top_old = max(0, min(1 - visible_height_old, zoom_center_y - visible_height_old / 2))

            mouse_img_x = left_old + mouse_norm_x * visible_width_old
            mouse_img_y = top_old + mouse_norm_y * visible_height_old

            zoom_factor = new_zoom
            zoom_center_x = mouse_img_x
            zoom_center_y = mouse_img_y

        print(f"Zoom: {zoom_factor:.1f}x")
        return

    # Double-click zoom
    if event == cv2.EVENT_LBUTTONDBLCLK:
        if zoom_factor < 10.0:
            visible_width = 1.0 / zoom_factor
            visible_height = 1.0 / zoom_factor
            left = max(0, min(1 - visible_width, zoom_center_x - visible_width / 2))
            top = max(0, min(1 - visible_height, zoom_center_y - visible_height / 2))

            click_norm_x = left + (x / display_width) * visible_width
            click_norm_y = top + (y / (h * resize_ratio)) * visible_height

            zoom_factor = min(zoom_factor + 2.0, 10.0)
            zoom_center_x = click_norm_x
            zoom_center_y = click_norm_y
        return

    # Regular left click
    if event == cv2.EVENT_LBUTTONDOWN:
        img_x, img_y = screen_to_image_coords(x, y, w, h)

        img_x = max(0, min(w - 1, img_x))
        img_y = max(0, min(h - 1, img_y))

        original_point = (img_x, img_y)
        clicked_points.append(original_point)
        print(f"Clicked: {original_point}")

        if len(clicked_points) == 2:
            pt1, pt2 = clicked_points
            pixel_dist = euclidean_distance(pt1, pt2)

            if mode == "reference":
                real_distance = float(input(f"Enter real-world distance between {pt1} and {pt2}: "))
                scale = real_distance / pixel_dist
                reference_scales.append(scale)
                reference_points.append((pt1, pt2))
                recompute_average_scale()
                print(f"Reference scale added: {scale:.6f}")
                print(f"Updated average scale: {average_scale:.6f}")

            elif mode == "target" and average_scale is not None:
                estimated_distance = pixel_dist * average_scale
                print(f"Measured: {pixel_dist:.2f} px -> {estimated_distance:.2f} units")
                measured_lines.append((pt1, pt2, estimated_distance))
            elif mode == "target" and average_scale is None:
                print("No reference scale available yet. Add reference pairs first.")

            clicked_points = []

def is_left_arrow(key):
    return key in (81, 2424832)

def is_right_arrow(key):
    return key in (83, 2555904)


# ---------------- Main Program ----------------
def main():
    global original_frame, resize_ratio, mode
    global image_paths, current_image_index
    global zoom_factor, zoom_center_x, zoom_center_y

    root = Tk()
    root.withdraw()
    selected_path = filedialog.askopenfilename(
        title="Select an Image",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")]
    )

    if not selected_path:
        print("No file selected.")
        return

    selected_path = Path(selected_path)
    image_paths = get_images_in_folder(selected_path)

    if not image_paths:
        print("No supported images found in the folder.")
        return

    try:
        current_image_index = image_paths.index(selected_path)
    except ValueError:
        current_image_index = 0

    if not load_image_by_index(current_image_index):
        return

    print("\n" + "=" * 60)
    print("CONTROLS:")
    print("  Click reference point pairs (in 'reference' mode)")
    print("  'm' = Switch to measurement mode")
    print("  'c' = Undo last item")
    print("        - pending click -> remove last clicked point")
    print("        - reference mode -> remove last reference pair from average")
    print("        - target mode -> remove last measured target line")
    print("  Mouse wheel = Zoom in/out towards cursor")
    print("  Double-click = Zoom to clicked area")
    print("  '+/-' = Zoom in/out")
    print("  'r' = Reset zoom to 1x")
    print("  'x' = Reset ALL (references + measurements)")
    print("  Left Arrow  = Previous image in folder")
    print("  Right Arrow = Next image in folder")
    print("  'Esc' or 'q' = Exit")
    print("=" * 60 + "\n")

    cv2.namedWindow("Distance Measurement")
    cv2.setMouseCallback("Distance Measurement", mouse_callback)

    while True:
        if original_frame is None:
            break

        h, w = original_frame.shape[:2]
        display_height = int(h * resize_ratio)

        visible_width = 1.0 / zoom_factor
        visible_height = 1.0 / zoom_factor

        left = zoom_center_x - visible_width / 2
        top = zoom_center_y - visible_height / 2

        left = max(0, min(1 - visible_width, left))
        top = max(0, min(1 - visible_height, top))

        x1 = int(left * w)
        y1 = int(top * h)
        x2 = int((left + visible_width) * w)
        y2 = int((top + visible_height) * h)

        cropped = original_frame[y1:y2, x1:x2].copy()
        display_frame = cv2.resize(cropped, (display_width, display_height))

        # Draw all reference pairs
        for pt1, pt2 in reference_points:
            screen_pt1 = image_to_screen_coords(pt1[0], pt1[1], w, h)
            screen_pt2 = image_to_screen_coords(pt2[0], pt2[1], w, h)

            if (0 <= screen_pt1[0] < display_width and 0 <= screen_pt1[1] < display_height):
                cv2.circle(display_frame, screen_pt1, 1, (0, 255, 0), 2)
            if (0 <= screen_pt2[0] < display_width and 0 <= screen_pt2[1] < display_height):
                cv2.circle(display_frame, screen_pt2, 1, (0, 255, 0), 2)

            if (0 <= screen_pt1[0] < display_width and 0 <= screen_pt1[1] < display_height and
                0 <= screen_pt2[0] < display_width and 0 <= screen_pt2[1] < display_height):
                cv2.line(display_frame, screen_pt1, screen_pt2, (0, 255, 0), 1)

        # Draw pending clicked points
        for pt in clicked_points:
            screen_pt = image_to_screen_coords(pt[0], pt[1], w, h)
            if 0 <= screen_pt[0] < display_width and 0 <= screen_pt[1] < display_height:
                cv2.circle(display_frame, screen_pt, 2, (0, 255, 255), -1)

        # Draw measured lines
        for pt1, pt2, dist in measured_lines:
            screen_pt1 = image_to_screen_coords(pt1[0], pt1[1], w, h)
            screen_pt2 = image_to_screen_coords(pt2[0], pt2[1], w, h)

            if (0 <= screen_pt1[0] < display_width and 0 <= screen_pt1[1] < display_height and
                0 <= screen_pt2[0] < display_width and 0 <= screen_pt2[1] < display_height):
                mid = ((screen_pt1[0] + screen_pt2[0]) // 2, (screen_pt1[1] + screen_pt2[1]) // 2)
                cv2.line(display_frame, screen_pt1, screen_pt2, (255, 0, 0), 2)
                cv2.putText(display_frame, f"{dist:.2f} units", mid,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        cv2.putText(display_frame, f"Mode: {mode.upper()} ('m' to switch)", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        cv2.putText(display_frame, f"References: {len(reference_points)}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        cv2.putText(display_frame, f"Measurements: {len(measured_lines)}", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
        cv2.putText(display_frame, f"Image: {current_image_index + 1}/{len(image_paths)}", (10, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

        cv2.imshow("Distance Measurement", display_frame)

        key = cv2.waitKeyEx(1)

        if key == 27 or key == ord('q'):
            break
        elif key == ord('m'):
            mode = "target" if mode == "reference" else "reference"
            print(f"Switched mode to: {mode}")
        elif key == ord('c'):
            undo_last()
        elif key == ord('+') or key == ord('='):
            zoom_factor = min(zoom_factor + 0.5, 10.0)
            print(f"Zoom: {zoom_factor:.1f}x")
        elif key == ord('-') or key == ord('_'):
            zoom_factor = max(zoom_factor - 0.5, 1.0)
            print(f"Zoom: {zoom_factor:.1f}x")
        elif key == ord('r'):
            reset_zoom()
            print("Zoom reset")
        elif key == ord('x'):
            reset_measurements()
            print("ALL data reset (references + measurements)")
        elif is_left_arrow(key):
            if current_image_index > 0:
                load_image_by_index(current_image_index - 1)
            else:
                print("Already at first image.")
        elif is_right_arrow(key):
            if current_image_index < len(image_paths) - 1:
                load_image_by_index(current_image_index + 1)
            else:
                print("Already at last image.")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()