package com.civicservices.monitor

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private var detector: Detector? = null
    private lateinit var reporter: IncidentReporter
    private lateinit var overlayView: OverlayView
    private lateinit var statusText: TextView
    private lateinit var recordingIndicator: TextView
    private lateinit var recordButton: ImageButton
    private lateinit var captureButton: ImageButton
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private val mainHandler = Handler(Looper.getMainLooper())

    private var videoCapture: VideoCapture<Recorder>? = null
    private var activeRecording: Recording? = null
    private var recordingStartMs = 0L

    // Latest upright frame the detector just processed, reused for manual photo capture so a
    // snapshot matches exactly what's on screen (same rotation-corrected frame, no separate
    // ImageCapture use case needed alongside Preview+ImageAnalysis+VideoCapture).
    @Volatile private var latestFrame: Bitmap? = null

    private var lastFrameTime = 0L
    private val cameraId = "phone-1"

    private val requestPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startCamera() else statusText.text = "Camera permission denied"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        ThemePrefs.applySavedMode(this)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        overlayView = findViewById(R.id.overlayView)
        statusText = findViewById(R.id.statusText)
        recordingIndicator = findViewById(R.id.recordingIndicator)
        recordButton = findViewById(R.id.recordButton)
        captureButton = findViewById(R.id.captureButton)
        reporter = IncidentReporter(this)

        findViewById<ImageButton>(R.id.aboutButton).setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }
        findViewById<ImageButton>(R.id.backButton).setOnClickListener { finish() }
        captureButton.setOnClickListener { capturePhoto() }
        recordButton.setOnClickListener { toggleRecording() }

        detector = try {
            Detector(this)
        } catch (e: Exception) {
            statusText.text = "No model.tflite in assets/ — camera preview only, no detection"
            null
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            requestPermission.launch(Manifest.permission.CAMERA)
        }
    }

    /**
     * One binding used the whole time the screen is open: Preview + ImageAnalysis (detector)
     * + VideoCapture, all live simultaneously. Recording used to unbind ImageAnalysis entirely
     * (dropping live detection while recording) — this binds all three up front instead, so
     * starting/stopping a recording is just starting/stopping the Recorder, no camera rebind.
     */
    private fun startCamera() {
        val previewView = findViewById<PreviewView>(R.id.previewView)
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val provider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            val analysis = ImageAnalysis.Builder()
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(cameraExecutor) { imageProxy -> analyzeFrame(imageProxy) }

            val recorder = Recorder.Builder().build()
            val capture = VideoCapture.withOutput(recorder)
            videoCapture = capture

            provider.unbindAll()
            provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis, capture)
        }, ContextCompat.getMainExecutor(this))
    }

    private fun capturePhoto() {
        val frame = latestFrame
        if (frame == null) {
            Toast.makeText(this, "No frame yet, try again", Toast.LENGTH_SHORT).show()
            return
        }
        val file = File(MediaVault.todayDir(this), "CIVIC_${System.currentTimeMillis()}.jpg")
        file.outputStream().use { out -> frame.compress(Bitmap.CompressFormat.JPEG, 92, out) }
        Toast.makeText(this, "Photo saved", Toast.LENGTH_SHORT).show()
    }

    private val timerTick = object : Runnable {
        override fun run() {
            val elapsed = (System.currentTimeMillis() - recordingStartMs) / 1000
            recordingIndicator.text = String.format(Locale.US, "● REC %02d:%02d", elapsed / 60, elapsed % 60)
            mainHandler.postDelayed(this, 1000)
        }
    }

    private fun toggleRecording() {
        val existing = activeRecording
        if (existing != null) {
            existing.stop()
            activeRecording = null
            return
        }

        val capture = videoCapture ?: return
        val file = File(MediaVault.todayDir(this), "CIVIC_${System.currentTimeMillis()}.mp4")
        val outputOptions = FileOutputOptions.Builder(file).build()

        activeRecording = capture.output
            .prepareRecording(this, outputOptions)
            .start(ContextCompat.getMainExecutor(this)) { event ->
                when (event) {
                    is VideoRecordEvent.Start -> {
                        recordingStartMs = System.currentTimeMillis()
                        recordingIndicator.visibility = android.view.View.VISIBLE
                        mainHandler.post(timerTick)
                    }
                    is VideoRecordEvent.Finalize -> {
                        mainHandler.removeCallbacks(timerTick)
                        recordingIndicator.visibility = android.view.View.GONE
                        val message = if (event.hasError()) "Recording failed" else "Video saved"
                        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
                    }
                    else -> {}
                }
            }
    }

    private fun analyzeFrame(imageProxy: ImageProxy) {
        val activeDetector = detector
        if (activeDetector == null) {
            imageProxy.close()
            return
        }

        val bitmap = imageProxy.toUprightBitmap()
        latestFrame = bitmap
        // The 16-class model (2026-09-07) predicts streetlight_working vs
        // streetlight_not_working directly, so the NightLightChecker brightness
        // heuristic it used to depend on is gone from this path. That workaround only
        // existed because no dataset labelled lit/unlit streetlights; ours now does,
        // and it works in daylight too — the old code discarded every streetlight
        // detection before 19:00 because the heuristic could not judge them.
        val finalDetections = activeDetector.detect(bitmap)

        // Healthy states (manhole_closed, streetlight_working) are still drawn, so you
        // can see the model looked, but they are not civic incidents.
        finalDetections
            .filter { it.label in Detector.ISSUE_CLASSES }
            .forEach { reporter.maybeReport(bitmap, it, cameraId) }

        val now = System.currentTimeMillis()
        val fps = if (lastFrameTime > 0) 1000f / (now - lastFrameTime) else 0f
        lastFrameTime = now

        runOnUiThread {
            overlayView.update(finalDetections, bitmap.width, bitmap.height)
            statusText.text = "%.1f FPS  •  %d detections".format(fps, finalDetections.size)
        }

        imageProxy.close()
    }

    /**
     * ImageAnalysis delivers frames in the camera sensor's native orientation (landscape on
     * most phones), NOT the upright orientation CameraX's Preview auto-corrects for display.
     * Without rotating here, a phone held in portrait feeds the model sideways frames it was
     * never trained on — which was silently biasing every detection toward one class.
     */
    private fun ImageProxy.toUprightBitmap(): Bitmap {
        val buffer = planes[0].buffer
        val raw = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        raw.copyPixelsFromBuffer(buffer)

        val rotation = imageInfo.rotationDegrees
        if (rotation == 0) return raw

        val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
        return Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true)
    }

    override fun onDestroy() {
        super.onDestroy()
        activeRecording?.stop()
        mainHandler.removeCallbacks(timerTick)
        detector?.close()
        cameraExecutor.shutdown()
    }
}
