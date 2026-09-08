# Civic Services Monitor — Android app

Native on-device app: CameraX live preview + a TFLite YOLO11n detector running directly
on the phone (no server, no network needed once the model is trained). Verified building
successfully on this machine with a local JDK 17 + Android SDK toolchain (see below) —
`app/build/outputs/apk/debug/app-debug.apk` already exists from that build.

## Source layout

```
app/src/main/java/com/civicservices/monitor/
  MainActivity.kt        CameraX capture loop, wires everything together
  Detector.kt             TFLite Interpreter wrapper: preprocess, decode YOLO output, NMS
  OverlayView.kt           draws boxes/labels over the camera preview
  NightLightChecker.kt    Kotlin port of streetlight/classify_lit_state.py (brightness heuristic)
  IncidentReporter.kt      on-device port of reporting/report.py — saves crop+JSON per incident
app/src/main/assets/       drop your trained model.tflite here (see PLACE_MODEL_HERE.txt)
```

Reports land in the phone's app-private storage:
`Android/data/com.civicservices.monitor/files/reports/` (visible via a file manager, or
`adb pull`).

## Toolchain used to build this (already set up on this machine)

- JDK 17 (Temurin) at `~/android-toolchain/jdk`
- Android SDK (platform-tools, android-34, build-tools 34.0.0) at `~/android-toolchain/sdk`
- Gradle 8.7, wrapped into this project's `./gradlew`

No Android Studio GUI was installed — everything here builds from the terminal. If you'd
also like the GUI IDE for editing, download it separately from
https://developer.android.com/studio and point it at this `android_app/` folder; it will
reuse the same `local.properties` SDK path.

## Build & install on your Samsung S24

1. **On the S24:** Settings → About phone → tap "Build number" 7 times to unlock Developer
   options. Then Settings → Developer options → enable **USB debugging**.
2. Connect the phone to this computer with a USB cable. Choose "File transfer / Android
   Auto" (not "charging only") if prompted, and tap **Allow** on the "Allow USB debugging?"
   popup that appears on the phone (approve the RSA key).
3. From this directory:
   ```
   export JAVA_HOME=~/android-toolchain/jdk
   export ANDROID_HOME=~/android-toolchain/sdk
   export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH

   adb devices              # should list your S24, not "unauthorized"
   ./gradlew installDebug   # builds + installs in one step
   ```
4. Open "Civic Monitor" on the phone, grant the camera permission when asked.

Without a trained `model.tflite` in `app/src/main/assets/`, the app still launches and
shows the live camera preview — it just skips detection (see PLACE_MODEL_HERE.txt) rather
than crashing. Once you've run `train.py` + `export.py` at the project root, copy
`best_float16.tflite` in as `model.tflite`, rebuild with `./gradlew installDebug`, and
you'll get live boxes for all 7 classes on-device.
