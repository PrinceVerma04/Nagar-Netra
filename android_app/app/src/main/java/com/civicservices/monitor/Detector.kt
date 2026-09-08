package com.civicservices.monitor

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.RectF
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.support.common.FileUtil
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

data class Detection(val classId: Int, val label: String, val confidence: Float, val box: RectF)

/**
 * Wraps a YOLO11-family TFLite export (output shape [1, 4+numClasses, numAnchors], no
 * objectness channel) with manual decode + NMS, since a raw Interpreter export has no
 * bundled metadata for the TFLite Task library to use automatically.
 */
class Detector(context: Context, modelPath: String = "model.tflite") {

    // Must match configs/data.yaml order exactly (ids 0-15, contiguous). Retrained
    // 2026-09-07: the 7-class taxonomy was replaced by 16 classes — `cattle` split
    // into the individual species, and the two coarse classes below split into their
    // real states, which the model now predicts directly.
    val labels = listOf(
        "garbage_pile",              // 0
        "pothole",                   // 1
        "encroachment",              // 2
        "billboard_hoarding",        // 3
        "cow",                       // 4
        "manhole_closed",            // 5
        "manhole_open",              // 6
        "manhole_broken",            // 7
        "streetlight_working",       // 8
        "streetlight_not_working",   // 9
        "cat",                       // 10
        "horse",                     // 11
        "dog",                       // 12
        "buffalo",                   // 13
        "goat",                      // 14
        "camel",                     // 15
    )

    companion object {
        /**
         * Classes that represent an actual civic issue worth filing a report for.
         * `manhole_closed` and `streetlight_working` are the healthy states — the model
         * detects them so the overlay can show it looked and found nothing wrong, but
         * filing an incident for a perfectly good streetlight would flood the report log.
         */
        val ISSUE_CLASSES = setOf(
            "garbage_pile", "pothole", "encroachment", "billboard_hoarding",
            "manhole_open", "manhole_broken", "streetlight_not_working",
            "cow", "cat", "horse", "dog", "buffalo", "goat", "camel",
        )

        /** Healthy states — detected and drawn, never reported. */
        val OK_CLASSES = setOf("manhole_closed", "streetlight_working")
    }

    private val interpreter: Interpreter
    private val inputSize: Int
    private val nchw: Boolean // Ultralytics' TFLite export is [1,3,H,W] (channels-first), not the [1,H,W,3] TFLite default
    private val numClasses: Int
    private val numAnchors: Int

    init {
        val model = FileUtil.loadMappedFile(context, modelPath)
        interpreter = Interpreter(model, Interpreter.Options().apply { setNumThreads(4) })

        val inputShape = interpreter.getInputTensor(0).shape()
        nchw = inputShape[1] == 3
        inputSize = if (nchw) inputShape[2] else inputShape[1]

        val outputShape = interpreter.getOutputTensor(0).shape() // [1, 4+numClasses, numAnchors]
        numClasses = outputShape[1] - 4
        numAnchors = outputShape[2]
    }

    fun detect(bitmap: Bitmap, confThreshold: Float = 0.4f, iouThreshold: Float = 0.45f): List<Detection> {
        // LETTERBOX, never stretch. This used to be
        //     Bitmap.createScaledBitmap(bitmap, inputSize, inputSize, true)
        // which squashes a 4:3 camera frame into a square and distorts every object -
        // a round manhole cover arrives as an ellipse. Ultralytics letterboxes (pads
        // to square, preserving aspect) for both training and validation, so stretching
        // fed the model a geometry it was never trained on. Measured off-device:
        // matching the training geometry lifted the hit rate on unseen photos from
        // 34% to 43% with no retraining.
        val scale = min(inputSize.toFloat() / bitmap.width, inputSize.toFloat() / bitmap.height)
        val scaledW = (bitmap.width * scale).roundToInt().coerceAtLeast(1)
        val scaledH = (bitmap.height * scale).roundToInt().coerceAtLeast(1)
        val padX = (inputSize - scaledW) / 2f
        val padY = (inputSize - scaledH) / 2f

        val letterboxed = Bitmap.createBitmap(inputSize, inputSize, Bitmap.Config.ARGB_8888)
        Canvas(letterboxed).apply {
            drawColor(Color.rgb(114, 114, 114))   // the grey Ultralytics pads with
            drawBitmap(Bitmap.createScaledBitmap(bitmap, scaledW, scaledH, true),
                       padX, padY, null)
        }
        val input = bitmapToByteBuffer(letterboxed)
        val output = Array(1) { Array(4 + numClasses) { FloatArray(numAnchors) } }
        try {
            interpreter.run(input, output)
        } catch (e: IllegalStateException) {
            // Interpreter was closed mid-flight by a concurrent mode switch (e.g. starting a
            // video recording) — drop this one frame instead of crashing the whole app.
            return emptyList()
        }

        // Ultralytics TFLite exports sometimes emit box coords normalized to [0,1] and
        // sometimes in input-pixel space depending on export flags — detect which at runtime.
        var maxCoord = 0f
        for (a in 0 until numAnchors) {
            maxCoord = max(maxCoord, max(output[0][0][a], output[0][1][a]))
        }
        val coordScale = if (maxCoord <= 1.5f) inputSize.toFloat() else 1f

        val candidates = mutableListOf<Detection>()
        for (a in 0 until numAnchors) {
            var bestClass = -1
            var bestScore = 0f
            for (c in 0 until numClasses) {
                val score = output[0][4 + c][a]
                if (score > bestScore) {
                    bestScore = score
                    bestClass = c
                }
            }
            if (bestScore < confThreshold) continue

            // Undo the letterbox: strip the padding, then divide by the scale factor.
            // (The old code multiplied by width/inputSize, which is only correct for a
            // stretch — with padding it would place every box in the wrong spot.)
            val cx = (output[0][0][a] * coordScale - padX) / scale
            val cy = (output[0][1][a] * coordScale - padY) / scale
            val w = output[0][2][a] * coordScale / scale
            val h = output[0][3][a] * coordScale / scale

            val box = RectF(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            candidates.add(Detection(bestClass, labels.getOrElse(bestClass) { "class_$bestClass" }, bestScore, box))
        }

        return nonMaxSuppression(candidates, iouThreshold)
    }

    private fun nonMaxSuppression(detections: List<Detection>, iouThreshold: Float): List<Detection> {
        val sorted = detections.sortedByDescending { it.confidence }.toMutableList()
        val kept = mutableListOf<Detection>()
        while (sorted.isNotEmpty()) {
            val best = sorted.removeAt(0)
            kept.add(best)
            sorted.removeAll { it.classId == best.classId && iou(best.box, it.box) > iouThreshold }
        }
        return kept
    }

    private fun iou(a: RectF, b: RectF): Float {
        val interLeft = max(a.left, b.left)
        val interTop = max(a.top, b.top)
        val interRight = min(a.right, b.right)
        val interBottom = min(a.bottom, b.bottom)
        val interArea = max(0f, interRight - interLeft) * max(0f, interBottom - interTop)
        val union = a.width() * a.height() + b.width() * b.height() - interArea
        return if (union <= 0f) 0f else interArea / union
    }

    private fun bitmapToByteBuffer(bitmap: Bitmap): ByteBuffer {
        val buffer = ByteBuffer.allocateDirect(4 * inputSize * inputSize * 3)
        buffer.order(ByteOrder.nativeOrder())
        val pixels = IntArray(inputSize * inputSize)
        bitmap.getPixels(pixels, 0, inputSize, 0, 0, inputSize, inputSize)

        if (nchw) {
            // channel-planar: all R, then all G, then all B
            for (channelShift in intArrayOf(16, 8, 0)) {
                for (pixel in pixels) {
                    buffer.putFloat(((pixel shr channelShift) and 0xFF) / 255f)
                }
            }
        } else {
            // interleaved per pixel: R,G,B, R,G,B, ...
            for (pixel in pixels) {
                buffer.putFloat(((pixel shr 16) and 0xFF) / 255f)
                buffer.putFloat(((pixel shr 8) and 0xFF) / 255f)
                buffer.putFloat((pixel and 0xFF) / 255f)
            }
        }
        buffer.rewind()
        return buffer
    }

    fun close() = interpreter.close()
}
