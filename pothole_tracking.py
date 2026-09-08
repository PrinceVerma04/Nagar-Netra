"""
Pothole tracking & unique-count from video, using ByteTrack.

A plain per-frame detector (live_monitor.py) re-reports the same physical pothole on
every frame it stays in view. This script instead assigns each pothole a persistent
tracking ID across frames (Ultralytics' built-in ByteTrack via model.track(..., persist=True))
so a single drive-through video yields one count per real pothole, not one per frame.
Approach adapted from https://github.com/Satyam300702/pothole-detection-yolo-2 (their
Count_file.py / ui2.py), ported onto our multi-class civic-services model instead of a
pothole-only one: detection here is filtered to the "pothole" class id so the other 6
classes don't affect tracking.

Usage:
    python pothole_tracking.py --source road_survey.mp4
    python pothole_tracking.py --source road_survey.mp4 --save-video annotated.mp4 --no-display
"""
import argparse
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reporting.report import save_incident

POTHOLE_CLASS_NAME = "pothole"


def parse_source(raw: str):
    return int(raw) if raw.isdigit() else raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="0", help="webcam index, video path, or phone/IP camera URL")
    parser.add_argument("--weights", default="runs/detect/runs/civic_services-3/weights/best.pt")
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--camera-id", default="camera-1")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--save-video", default=None, help="path to write the annotated output video")
    parser.add_argument("--no-display", action="store_true", help="run headless, no cv2 window")
    parser.add_argument("--no-report", action="store_true", help="skip writing an incident report per new pothole")
    args = parser.parse_args()

    model = YOLO(args.weights)
    if POTHOLE_CLASS_NAME not in model.names.values():
        raise SystemExit(f"'{POTHOLE_CLASS_NAME}' is not a class in {args.weights} (found: {list(model.names.values())})")
    pothole_class_id = next(i for i, name in model.names.items() if name == POTHOLE_CLASS_NAME)

    source = parse_source(args.source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open source: {args.source}")

    writer = None
    if args.save_video:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(args.save_video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    unique_pothole_ids = set()
    reported_ids = set()

    print(f"Tracking potholes from {args.source} — press 'q' to stop (or Ctrl+C if --no-display).")
    try:
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break

            results = model.track(
                frame,
                conf=args.conf,
                imgsz=args.imgsz,
                classes=[pothole_class_id],
                tracker="bytetrack.yaml",
                persist=True,
                verbose=False,
            )[0]

            if results.boxes.id is not None:
                track_ids = results.boxes.id.int().cpu().tolist()
                for track_id, box, conf in zip(track_ids, results.boxes.xyxy.cpu().tolist(), results.boxes.conf.cpu().tolist()):
                    unique_pothole_ids.add(track_id)
                    if not args.no_report and track_id not in reported_ids:
                        x1, y1, x2, y2 = map(int, box)
                        save_incident(frame, (x1, y1, x2, y2), "pothole", conf, args.camera_id, args.lat, args.lon)
                        reported_ids.add(track_id)
                        print(f"[new pothole #{track_id}] conf={conf:.2f} total_unique={len(unique_pothole_ids)}")

            annotated = results.plot()
            cv2.rectangle(annotated, (10, 10), (330, 55), (0, 0, 0), -1)
            cv2.putText(
                annotated, f"Unique potholes: {len(unique_pothole_ids)}", (20, 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
            )

            if writer:
                writer.write(annotated)
            if not args.no_display:
                cv2.imshow("pothole tracking", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()

    print("--------------------------------")
    print("Total unique potholes:", len(unique_pothole_ids))
    print("--------------------------------")


if __name__ == "__main__":
    main()
