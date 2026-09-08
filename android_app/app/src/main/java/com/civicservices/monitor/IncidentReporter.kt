package com.civicservices.monitor

import android.content.Context
import android.graphics.Bitmap
import android.graphics.RectF
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * On-device counterpart to reporting/report.py: saves a cropped snapshot + one JSON
 * line per confirmed detection under MediaVault's date-organized storage, gated by a
 * per-class cooldown so a still-visible object doesn't spam reports every frame.
 */
class IncidentReporter(private val context: Context) {

    private val cooldownMillis = 60_000L
    private val lastReported = mutableMapOf<String, Long>()

    fun maybeReport(bitmap: Bitmap, detection: Detection, cameraId: String) {
        val now = System.currentTimeMillis()
        val last = lastReported[detection.label] ?: 0L
        if (now - last < cooldownMillis) return
        lastReported[detection.label] = now

        val timestamp = SimpleDateFormat("yyyyMMdd'T'HHmmss", Locale.US).format(Date())
        val stem = "${timestamp}_${detection.label}_$cameraId"
        val reportsDir = MediaVault.todayDir(context)

        val box = detection.box
        val crop = safeCrop(bitmap, box)
        File(reportsDir, "$stem.jpg").outputStream().use { out ->
            crop.compress(Bitmap.CompressFormat.JPEG, 90, out)
        }

        val json = """
            {
              "class": "${detection.label}",
              "confidence": ${"%.3f".format(detection.confidence)},
              "timestamp": "${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())}",
              "camera_id": "$cameraId",
              "image": "$stem.jpg"
            }
        """.trimIndent()
        File(reportsDir, "$stem.json").writeText(json)
    }

    private fun safeCrop(bitmap: Bitmap, box: RectF): Bitmap {
        val left = box.left.toInt().coerceIn(0, bitmap.width - 1)
        val top = box.top.toInt().coerceIn(0, bitmap.height - 1)
        val right = box.right.toInt().coerceIn(left + 1, bitmap.width)
        val bottom = box.bottom.toInt().coerceIn(top + 1, bitmap.height)
        return Bitmap.createBitmap(bitmap, left, top, right - left, bottom - top)
    }
}
