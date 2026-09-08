package com.civicservices.monitor

import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.content.Intent
import android.os.Bundle
import android.view.animation.OvershootInterpolator
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class SplashActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        ThemePrefs.applySavedMode(this)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)

        Thread { MediaVault.cleanupOldData(applicationContext) }.start()

        val logo = findViewById<ImageView>(R.id.logoMark)
        val brand = findViewById<TextView>(R.id.brandText)
        val tagline = findViewById<TextView>(R.id.taglineText)

        val logoScaleX = ObjectAnimator.ofFloat(logo, "scaleX", 0.6f, 1.08f, 1f).apply { duration = 700 }
        val logoScaleY = ObjectAnimator.ofFloat(logo, "scaleY", 0.6f, 1.08f, 1f).apply { duration = 700 }
        val logoAlpha = ObjectAnimator.ofFloat(logo, "alpha", 0f, 1f).apply { duration = 500 }
        val logoRotate = ObjectAnimator.ofFloat(logo, "rotation", -12f, 0f).apply {
            duration = 700
            interpolator = OvershootInterpolator(2f)
        }

        val brandAlpha = ObjectAnimator.ofFloat(brand, "alpha", 0f, 1f).apply {
            duration = 400
            startDelay = 400
        }
        val brandTranslate = ObjectAnimator.ofFloat(brand, "translationY", 24f, 0f).apply {
            duration = 400
            startDelay = 400
        }
        val taglineAlpha = ObjectAnimator.ofFloat(tagline, "alpha", 0f, 1f).apply {
            duration = 400
            startDelay = 650
        }

        AnimatorSet().apply {
            playTogether(logoScaleX, logoScaleY, logoAlpha, logoRotate, brandAlpha, brandTranslate, taglineAlpha)
            start()
        }

        logo.postDelayed({
            startActivity(Intent(this, LandingActivity::class.java))
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
            finish()
        }, 1400)
    }
}
