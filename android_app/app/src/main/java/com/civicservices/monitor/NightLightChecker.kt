package com.civicservices.monitor

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.RectF
import java.util.Calendar

/**
 * Kotlin port of streetlight/classify_lit_state.py: no dataset labels streetlights
 * lit/unlit (see DATASETS.md), so state is inferred from crop brightness at night.
 */
object NightLightChecker {

    private const val BRIGHTNESS_THRESHOLD = 140  // mean value channel, 0-255
    private const val HALO_RATIO_THRESHOLD = 0.15f

    fun isNighttime(): Boolean {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        return hour >= 19 || hour < 6
    }

    fun isLit(bitmap: Bitmap, box: RectF): Boolean {
        val left = box.left.toInt().coerceIn(0, bitmap.width - 1)
        val top = box.top.toInt().coerceIn(0, bitmap.height - 1)
        val right = box.right.toInt().coerceIn(left + 1, bitmap.width)
        val bottom = box.bottom.toInt().coerceIn(top + 1, bitmap.height)
        val cropWidth = right - left
        val cropHeight = bottom - top
        if (cropWidth <= 0 || cropHeight <= 0) return false

        val pixels = IntArray(cropWidth * cropHeight)
        bitmap.getPixels(pixels, 0, cropWidth, left, top, cropWidth, cropHeight)

        var brightnessSum = 0L
        var haloCount = 0
        val hsv = FloatArray(3)
        for (pixel in pixels) {
            Color.colorToHSV(pixel, hsv)
            val value = (hsv[2] * 255).toInt()
            brightnessSum += value
            if (value > 230) haloCount++
        }

        val meanBrightness = brightnessSum.toFloat() / pixels.size
        val haloRatio = haloCount.toFloat() / pixels.size
        return meanBrightness > BRIGHTNESS_THRESHOLD || haloRatio > HALO_RATIO_THRESHOLD
    }
}
