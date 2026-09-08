package com.civicservices.monitor

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View

// Red = a hazard someone could be hurt by. Updated for the 16-class model: the coarse
// manhole_open_broken split into open/broken (both hazards), and non-working
// streetlights are now a predicted class rather than a "_non_working" label suffix
// synthesised by the old brightness heuristic.
private val DAMAGE_CLASSES = setOf(
    "pothole", "manhole_open", "manhole_broken", "streetlight_not_working",
)

// Healthy states get a neutral blue so they read as "checked, fine" rather than as a
// green pass on something that might actually be an issue.
private val OK_CLASSES = setOf("manhole_closed", "streetlight_working")

class OverlayView(context: Context, attrs: AttributeSet? = null) : View(context, attrs) {

    private var detections: List<Detection> = emptyList()
    private var sourceWidth = 1
    private var sourceHeight = 1

    private val boxPaint = Paint().apply { style = Paint.Style.STROKE; strokeWidth = 6f }
    private val textPaint = Paint().apply { color = Color.WHITE; textSize = 42f }
    private val textBgPaint = Paint().apply { color = Color.argb(180, 0, 0, 0) }

    fun update(newDetections: List<Detection>, srcWidth: Int, srcHeight: Int) {
        detections = newDetections
        sourceWidth = srcWidth
        sourceHeight = srcHeight
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (detections.isEmpty()) return

        val scaleX = width.toFloat() / sourceWidth
        val scaleY = height.toFloat() / sourceHeight

        for (detection in detections) {
            boxPaint.color = when (detection.label) {
                in DAMAGE_CLASSES -> Color.RED
                in OK_CLASSES -> Color.parseColor("#2979FF")
                else -> Color.parseColor("#00C853")
            }

            val left = detection.box.left * scaleX
            val top = detection.box.top * scaleY
            val right = detection.box.right * scaleX
            val bottom = detection.box.bottom * scaleY
            canvas.drawRect(left, top, right, bottom, boxPaint)

            val label = "${detection.label} ${(detection.confidence * 100).toInt()}%"
            val textWidth = textPaint.measureText(label)
            canvas.drawRect(left, top - 50f, left + textWidth + 16f, top, textBgPaint)
            canvas.drawText(label, left + 8f, top - 12f, textPaint)
        }
    }
}
