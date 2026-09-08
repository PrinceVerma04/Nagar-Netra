package com.civicservices.monitor

import android.os.Bundle
import android.widget.RadioGroup
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate

class AboutActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        ThemePrefs.applySavedMode(this)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_about)

        val group = findViewById<RadioGroup>(R.id.themeRadioGroup)
        val radioSystem = findViewById<android.widget.RadioButton>(R.id.radioSystem)
        val radioLight = findViewById<android.widget.RadioButton>(R.id.radioLight)
        val radioDark = findViewById<android.widget.RadioButton>(R.id.radioDark)

        when (ThemePrefs.currentMode(this)) {
            AppCompatDelegate.MODE_NIGHT_YES -> radioDark.isChecked = true
            AppCompatDelegate.MODE_NIGHT_NO -> radioLight.isChecked = true
            else -> radioSystem.isChecked = true
        }

        group.setOnCheckedChangeListener { _, checkedId ->
            val mode = when (checkedId) {
                R.id.radioLight -> AppCompatDelegate.MODE_NIGHT_NO
                R.id.radioDark -> AppCompatDelegate.MODE_NIGHT_YES
                else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            }
            ThemePrefs.setMode(this, mode)
            recreate()
        }
    }
}
