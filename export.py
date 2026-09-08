"""
Exports the trained weights to the mobile-ready formats.
INT8 TFLite is the target for Android; CoreML float16 for iOS.

Usage:
    python export.py --weights runs/civic_services/weights/best.pt
"""
import argparse
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="runs/civic_services/weights/best.pt")
    parser.add_argument("--data", default="configs/data.yaml")
    args = parser.parse_args()

    model = YOLO(args.weights)

    model.export(format="tflite", int8=True, data=args.data, imgsz=640)

    try:
        # coremltools' blob-writer backend is macOS-native; this always fails on Linux.
        model.export(format="coreml", half=True, imgsz=640)
    except Exception as exc:
        print(f"[skip] CoreML export failed (expected on Linux, needs macOS): {exc}")

    model.export(format="onnx", simplify=True, imgsz=640)

    print("Exports written next to the source weights (best_saved_model/, best.onnx, best.mlpackage if on macOS).")


if __name__ == "__main__":
    main()
