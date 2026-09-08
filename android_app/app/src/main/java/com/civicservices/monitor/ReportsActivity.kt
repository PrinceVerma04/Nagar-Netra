package com.civicservices.monitor

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.CheckBox
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.io.File

class ReportsActivity : AppCompatActivity() {

    private val selected = mutableSetOf<File>()
    private lateinit var exportButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        ThemePrefs.applySavedMode(this)
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_reports)

        findViewById<ImageButton>(R.id.backButton).setOnClickListener { finish() }
        exportButton = findViewById(R.id.exportButton)
        exportButton.setOnClickListener { exportSelected() }

        val container = findViewById<LinearLayout>(R.id.reportsContainer)
        val dateFolders = MediaVault.listDateFolders(this)

        if (dateFolders.isEmpty()) {
            container.addView(TextView(this).apply {
                text = "No media yet. Start live monitoring, or capture a photo/video, to see it here."
                textSize = 14f
                gravity = Gravity.CENTER
                setPadding(0, 80, 0, 0)
            })
            return
        }

        for (dateDir in dateFolders) {
            container.addView(TextView(this).apply {
                text = dateDir.name
                textSize = 15f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(getColor(R.color.brand_orange))
                setPadding(0, 24, 0, 8)
            })

            val mediaFiles = dateDir.listFiles { f ->
                f.extension.equals("jpg", true) || f.extension.equals("mp4", true)
            }?.sortedByDescending { it.lastModified() } ?: emptyList()

            for (file in mediaFiles) {
                container.addView(buildMediaRow(file))
            }
        }
    }

    private fun buildMediaRow(file: File): LinearLayout {
        val isVideo = file.extension.equals("mp4", true)
        val jsonFile = File(file.parentFile, file.nameWithoutExtension + ".json")
        val meta = if (jsonFile.isFile) runCatching { JSONObject(jsonFile.readText()) }.getOrNull() else null

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, 0, 0, 20)
        }

        val checkbox = CheckBox(this).apply {
            isChecked = file in selected
            setOnCheckedChangeListener { _, checked ->
                if (checked) selected.add(file) else selected.remove(file)
                exportButton.text = "Export (${selected.size})"
            }
        }

        val thumb = ImageView(this).apply {
            layoutParams = LinearLayout.LayoutParams(160, 160).apply { marginStart = 8 }
            scaleType = ImageView.ScaleType.CENTER_CROP
            setImageBitmap(if (isVideo) videoThumbnail(file) else decodeSampled(file, 160, 160))
        }

        val textColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = 16
            }
        }
        textColumn.addView(TextView(this).apply {
            text = when {
                meta != null -> meta.optString("class")
                isVideo -> "Video recording"
                else -> "Manual photo"
            }
            textSize = 15f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        if (meta != null) {
            textColumn.addView(TextView(this).apply { text = "Confidence: ${meta.optDouble("confidence")}"; textSize = 12f })
            textColumn.addView(TextView(this).apply { text = meta.optString("timestamp"); textSize = 12f })
            textColumn.addView(TextView(this).apply { text = "Camera: ${meta.optString("camera_id")}"; textSize = 12f })
        } else {
            textColumn.addView(TextView(this).apply {
                text = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US).format(file.lastModified())
                textSize = 12f
            })
        }

        row.addView(checkbox)
        row.addView(thumb)
        row.addView(textColumn)
        return row
    }

    private fun exportSelected() {
        if (selected.isEmpty()) {
            Toast.makeText(this, "Nothing selected", Toast.LENGTH_SHORT).show()
            return
        }
        val count = MediaVault.exportToPublicStorage(this, selected.toList())
        Toast.makeText(this, "Saved $count file(s) to Gallery/Files", Toast.LENGTH_SHORT).show()
        selected.clear()
        exportButton.text = "Export (0)"
        recreate()
    }

    private fun decodeSampled(file: File, reqWidth: Int, reqHeight: Int): Bitmap {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, options)

        var sampleSize = 1
        while (options.outWidth / sampleSize > reqWidth * 2 || options.outHeight / sampleSize > reqHeight * 2) {
            sampleSize *= 2
        }
        val loadOptions = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        return BitmapFactory.decodeFile(file.absolutePath, loadOptions)
    }

    private fun videoThumbnail(file: File): Bitmap? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            retriever.getFrameAtTime(0)
        } catch (e: Exception) {
            null
        } finally {
            retriever.release() // works on all API levels; MediaMetadataRetriever.close() is API 29+ only
        }
    }
}
