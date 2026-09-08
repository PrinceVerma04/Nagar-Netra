"""
Live civic-services monitoring loop. Reads frames from a webcam, a video file, or a
phone/IP camera stream, runs the detector, applies the streetlight lit/unlit post-process
at night, and writes an incident report (image + JSON) the first time each class is seen,
then again after a per-class cooldown so a lingering pothole doesn't spam reports.

--source accepts:
  0                                    laptop/desktop webcam
  path/to/video.mp4                    a recorded video file
  http://<phone-ip>:8080/video         Android "IP Webcam" app MJPEG stream
  rtsp://<phone-ip>:8554/live          apps exposing an RTSP stream (e.g. "RTSP Camera")

Connecting a phone (Android):
  1. Install the "IP Webcam" app, start the server, note the shown URL (same Wi-Fi as
     this machine).
  2. python live_monitor.py --source http://192.168.1.23:8080/video --camera-id phone-1

Connecting a phone (iOS): use an app like "IP Camera Lite" the same way; it exposes an
MJPEG/RTSP URL to pass as --source.

Before training on the merged 7-class dataset, --weights defaults to the stock
COCO-pretrained yolo11n.pt, which only overlaps our classes on 'cow' (mapped to
'cattle' here) — everything else needs the trained best.pt from train.py.

Usage:
    python live_monitor.py --source 0 --camera-id webcam-1
    python live_monitor.py --weights runs/civic_services/weights/best.pt --source <phone-url> \
        --camera-id junction-4 --lat 12.9716 --lon 77.5946
"""
import argparse
import datetime
import sys
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parent))
from streetlight.classify_lit_state import is_lit_by_brightness
from reporting.report import save_incident

STREETLIGHT_CLASS = "streetlight_pole"
DAMAGE_CLASSES = {"pothole", "manhole_open_broken"}
REPORT_COOLDOWN_SECONDS = 60  # per class, avoid re-reporting a still-visible object every frame

# stock COCO class -> our reporting label, used only when running un-fine-tuned yolo11n.pt
COCO_CLASS_ALIAS = {"cow": "cattle"}


def is_nighttime() -> bool:
    hour = datetime.datetime.now().hour
    return hour >= 19 or hour < 6


def parse_source(raw: str):
    return int(raw) if raw.isdigit() else raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="0", help="webcam index, video path, or phone/IP camera URL")
    parser.add_argument("--weights", default="yolo11n.pt")
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--camera-id", default="camera-1")
    parser.add_argument("--lat", type=float, default=None, help="static camera latitude, for report geocoding")
    parser.add_argument("--lon", type=float, default=None, help="static camera longitude, for report geocoding")
    parser.add_argument("--no-display", action="store_true", help="run headless, no cv2 window")
    args = parser.parse_args()

    model = YOLO(args.weights)
    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open source: {args.source}")

    last_reported = {}  # class_name -> last report time

    print(f"Streaming from {args.source} — press 'q' to stop (or Ctrl+C if --no-display).")
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break

            results = model.predict(frame, conf=args.conf, verbose=False)[0]

            for box in results.boxes:
                raw_name = results.names[int(box.cls)]
                cls_name = COCO_CLASS_ALIAS.get(raw_name, raw_name)
                confidence = float(box.conf)
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = cls_name

                if cls_name == STREETLIGHT_CLASS:
                    if not is_nighttime():
                        continue
                    lit = is_lit_by_brightness(frame, (x1, y1, x2, y2))
                    if lit:
                        continue  # only report the non-working ones
                    label = "streetlight_OUT"
                    cls_name = "streetlight_non_working"

                now = time.time()
                if now - last_reported.get(cls_name, 0) > REPORT_COOLDOWN_SECONDS:
                    save_incident(frame, (x1, y1, x2, y2), cls_name, confidence, args.camera_id, args.lat, args.lon)
                    last_reported[cls_name] = now
                    print(f"[report] {cls_name} ({confidence:.2f}) from {args.camera_id}")

                if not args.no_display:
                    color = (0, 0, 255) if cls_name in DAMAGE_CLASSES or "non_working" in cls_name else (0, 200, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            if not args.no_display:
                cv2.imshow("civic-services live", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
