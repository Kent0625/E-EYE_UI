"""Conservative U-Net frame selection; this is not a refraction predictor."""
import hashlib
import json
import math
import os
from pathlib import Path


def analyse_sequence(directory, frames, model):
    import cv2
    import numpy as np
    import onnxruntime as ort
    roi = os.environ.get('EEYE_PUPIL_ROI')
    if not roi:
        return dict(quality_status='unconfigured', message='Capture saved. Configure the eye crop before quality filtering.')
    x, y, width, height = map(int, roi.split(','))
    if min(x, y) < 0 or min(width, height) <= 0 or x+width > 640 or y+height > 480:
        raise ValueError('Eye crop must be inside the 640 by 480 capture frame.')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(model, sess_options=options, providers=['CPUExecutionProvider'])
    shape = session.get_inputs()[0].shape
    if shape != [1, 1, 256, 256]:
        raise ValueError('Pupil model must accept grayscale input [1,1,256,256].')
    valid, measurements = [], []
    threshold = float(os.environ.get('EEYE_PUPIL_THRESHOLD', '0.35'))
    minimum_sharpness = float(os.environ.get('EEYE_MIN_SHARPNESS', '20'))
    for entry in frames:
        gray = cv2.imread(str(directory / entry['file']), cv2.IMREAD_GRAYSCALE)
        crop = gray[y:y+height, x:x+width]
        resized = cv2.resize(crop, (256, 256))
        logits = session.run(None, {session.get_inputs()[0].name:
                                   resized.astype(np.float32)[None, None] / 255})[0][0, 0]
        mask = (1 / (1 + np.exp(-np.clip(logits, -80, 80))) >= threshold).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        area, perimeter = cv2.contourArea(contour), cv2.arcLength(contour, True)
        bx, by, bw, bh = cv2.boundingRect(contour)
        circularity = 4 * math.pi * area / perimeter**2 if perimeter else 0
        if not 100 < area < 45000 or circularity < 0.25 or min(bx, by) < 2 or bx+bw >= 254 or by+bh >= 254:
            continue
        pupil = np.zeros_like(mask)
        cv2.drawContours(pupil, [contour], -1, 1, -1)
        pixels = resized[pupil.astype(bool)]
        mean = float(pixels.mean())
        sharpness = float(cv2.Laplacian(resized[by:by+bh, bx:bx+bw], cv2.CV_64F).var())
        measure = dict(file=entry['file'], elapsed_s=entry['elapsed_s'], distance_cm=entry['cm'],
            pupil_diameter_px=float(2*math.sqrt(area/math.pi)*math.sqrt(width*height)/256),
            pupil_intensity_mean=mean, pupil_intensity_variance=float(pixels.var()),
            sharpness=sharpness, circularity=circularity,
            accepted=128 <= mean <= 200 and sharpness >= minimum_sharpness)
        measurements.append(measure)
        if measure['accepted']:
            valid.append(measure)
    selected = [valid[i] for i in np.linspace(0, len(valid)-1, 10, dtype=int)] if len(valid) >= 10 else []
    report = dict(model_sha256=hashlib.sha256(Path(model).read_bytes()).hexdigest(),
                  roi=[x,y,width,height], segmentation_threshold=threshold,
                  minimum_sharpness=minimum_sharpness,
                  calibration_status='quality thresholds require device validation',
                  measurements=measurements, selected_frames=selected)
    (directory / 'quality.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not selected:
        return dict(status='retake_needed', frames_used=len(valid), quality_status='failed',
                    error_reason='few_valid_frames', message='Fewer than ten frames passed quality filtering. Retake this eye.')
    return dict(frames_used=10, quality_status='passed',
                message='Ten frames selected. Refraction model is not installed; no diopter estimate was produced.')
