package com.civicservices.monitor

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.ImageButton
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup

private val DETECTABLE_CLASSES = listOf(
    "Garbage piles",
    "Potholes",
    "Open/broken manholes",
    "Non-working streetlights",
    "Encroachments",
    "Billboards & hoardings",
    "Cattle on road",
)

class LandingActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        ThemePrefs.applySavedMode(this)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_landing)

        findViewById<Button>(R.id.startMonitoringButton).setOnClickListener {
            startActivity(Intent(this, MainActivity::class.java))
        }
        findViewById<Button>(R.id.viewReportsButton).setOnClickListener {
            startActivity(Intent(this, ReportsActivity::class.java))
        }
        findViewById<ImageButton>(R.id.aboutButton).setOnClickListener {
            startActivity(Intent(this, AboutActivity::class.java))
        }

        val chipGroup = findViewById<ChipGroup>(R.id.chipContainer)
        DETECTABLE_CLASSES.forEach { label ->
            val chip = Chip(this).apply {
                text = label
                isClickable = false
                isCheckable = false
                setChipBackgroundColorResource(android.R.color.transparent)
                chipStrokeWidth = 2f
                setChipStrokeColorResource(R.color.brand_orange)
                setTextColor(getColor(R.color.brand_orange))
            }
            chipGroup.addView(chip)
        }
    }
}
