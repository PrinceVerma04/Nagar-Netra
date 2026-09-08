"""
Writes one incident report (cropped snapshot + JSON metadata) per confirmed detection:
class, confidence, timestamp, camera id, and location (raw coords, plus a reverse-geocoded
address when GOOGLE_MAPS_API_KEY is set). Matches the "automatically record incidents /
generate a report with image, camera details, and time of detection" requirement.
"""
import json
import time
from pathlib import Path

import cv2

from reporting.geocode import reverse_geocode

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def save_incident(
    frame,
    bbox: tuple[int, int, int, int],
    class_name: str,
    confidence: float,
    camera_id: str,
    lat: float | None = None,
    lon: float | None = None,
) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)

    x1, y1, x2, y2 = bbox
    crop = frame[max(0, y1):y2, max(0, x1):x2]

    ts = time.strftime("%Y%m%dT%H%M%S")
    stem = f"{ts}_{class_name}_{camera_id}"
    image_path = REPORTS_DIR / f"{stem}.jpg"
    cv2.imwrite(str(image_path), crop if crop.size else frame)

    address = reverse_geocode(lat, lon) if lat is not None and lon is not None else None

    metadata = {
        "class": class_name,
        "confidence": round(confidence, 3),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "camera_id": camera_id,
        "location": {"lat": lat, "lon": lon, "address": address},
        "image": image_path.name,
        "bbox": bbox,
    }
    json_path = REPORTS_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(metadata, indent=2))

    return json_path
