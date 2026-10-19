import time
import json
import io
import math
from PIL import Image, ImageDraw, ImageFont

def generate_mock_distance_events():
    """
    Simulates distance sensor stream at ~5 Hz following scripted sequence:
    too far -> approaching -> in range (10-15cm) -> drift out -> back in range
    """
    sequence = [
        # (cm, valid, state, duration_s)
        (18.5, True, "too_far", 1.5),
        (16.0, True, "too_far", 1.0),
        (14.2, True, "ok", 2.0),
        (12.8, True, "ok", 3.0),
        (8.9, True, "too_close", 1.2),
        (12.5, True, "ok", 4.0),
        (0.0, False, "invalid", 0.8),
        (13.1, True, "ok", 5.0)
    ]
    
    while True:
        for cm, valid, state, duration in sequence:
            steps = int(duration * 5)
            for _ in range(steps):
                # Add minor jitter ±0.1 cm
                jitter = 0.05 * math.sin(time.time() * 3)
                reading_cm = round(cm + jitter, 1) if valid else 0.0
                data = {
                    "cm": reading_cm,
                    "valid": valid,
                    "state": state,
                    "ts": time.time()
                }
                yield f"data: {json.dumps(data)}\n\n"
                time.sleep(0.2)

def generate_mock_mjpeg_stream():
    """
    Generates a mock MJPEG stream at ~10 fps for the live alignment preview.
    """
    frame_idx = 0
    while True:
        img = Image.new("RGB", (640, 480), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        
        # Draw camera alignment crosshair and pupil target
        cx, cy = 320, 240
        draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline=(15, 144, 120), width=2)
        draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(30, 41, 59), outline=(45, 212, 191), width=2)
        
        # Draw mock crescent simulation
        crescent_shift = int(10 * math.sin(frame_idx * 0.1))
        draw.arc([cx - 36 + crescent_shift, cy - 36, cx + 36 + crescent_shift, cy + 36], start=30, end=150, fill=(200, 230, 220), width=6)
        
        # Center reticle
        draw.line([cx - 15, cy, cx + 15, cy], fill=(148, 163, 184), width=1)
        draw.line([cx, cy - 15, cx, cy + 15], fill=(148, 163, 184), width=1)
        
        # Mock banner watermark
        draw.rectangle([10, 10, 150, 36], fill=(15, 144, 120))
        draw.text((18, 14), "MOCK PREVIEW", fill=(255, 255, 255))
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        frame_bytes = buf.getvalue()
        
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        frame_idx += 1
        time.sleep(0.1)

def ensure_sample_media(media_folder):
    """
    Generates sample pupil thumbnails for mock fixtures if they do not exist.
    """
    import os
    os.makedirs(media_folder, exist_ok=True)
    samples = ["OD_sample.jpg", "OS_sample.jpg", "precheck_crescent.jpg"]
    for s in samples:
        path = os.path.join(media_folder, s)
        if not os.path.exists(path):
            img = Image.new("RGB", (320, 320), color=(18, 24, 38))
            draw = ImageDraw.Draw(img)
            # Simulated pupil circle with crescent
            draw.ellipse([80, 80, 240, 240], fill=(28, 36, 52), outline=(15, 144, 120), width=2)
            draw.arc([88, 88, 232, 232], start=45, end=135, fill=(180, 210, 205), width=8)
            label = "OD PUPIL (MOCK)" if "OD" in s else ("OS PUPIL (MOCK)" if "OS" in s else "CRESCENT TEST (MOCK)")
            draw.rectangle([10, 10, 180, 32], fill=(15, 144, 120))
            draw.text((16, 14), label, fill=(255, 255, 255))
            img.save(path, format="JPEG", quality=85)
