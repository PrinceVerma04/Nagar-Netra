package com.civicservices.monitor

import android.content.ContentValues
import android.content.Context
import android.provider.MediaStore
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Single place all captured media lands: incident-report photos, manual photos, and manual
 * videos are all written under app-private storage, organized as media/<yyyy-MM-dd>/, and
 * auto-deleted after RETENTION_DAYS. Nothing is public (visible in the phone's Gallery/Files
 * app) until the user explicitly exports it from ReportsActivity — see exportToPublicStorage.
 */
object MediaVault {
    private const val RETENTION_DAYS = 7L
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd", Locale.US)

    fun baseDir(context: Context): File =
        File(context.getExternalFilesDir(null), "media").apply { mkdirs() }

    fun todayDir(context: Context): File {
        val dir = File(baseDir(context), dateFormat.format(Date()))
        dir.mkdirs()
        return dir
    }

    /** Deletes any date folder older than RETENTION_DAYS. Call once per app launch. */
    fun cleanupOldData(context: Context) {
        val cutoff = System.currentTimeMillis() - RETENTION_DAYS * 24 * 60 * 60 * 1000
        baseDir(context).listFiles()?.forEach { dateDir ->
            if (!dateDir.isDirectory) return@forEach
            val folderTime = runCatching { dateFormat.parse(dateDir.name)?.time }.getOrNull()
            if (folderTime != null && folderTime < cutoff) {
                dateDir.deleteRecursively()
            }
        }
    }

    /** Date folders newest-first, e.g. for a grouped gallery view. */
    fun listDateFolders(context: Context): List<File> =
        baseDir(context).listFiles { f -> f.isDirectory }?.sortedByDescending { it.name } ?: emptyList()

    /**
     * Copies the given files into the phone's public Pictures/CivicMonitor or
     * Movies/CivicMonitor (by extension) via MediaStore, so they show up in the system
     * Gallery/Files app and survive the app's own 7-day auto-cleanup.
     */
    fun exportToPublicStorage(context: Context, files: List<File>): Int {
        var count = 0
        for (file in files) {
            val isVideo = file.extension.equals("mp4", ignoreCase = true)
            val collection = if (isVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, file.nameWithoutExtension)
                put(MediaStore.MediaColumns.MIME_TYPE, if (isVideo) "video/mp4" else "image/jpeg")
                put(MediaStore.MediaColumns.RELATIVE_PATH, if (isVideo) "Movies/CivicMonitor" else "Pictures/CivicMonitor")
            }
            val uri = context.contentResolver.insert(collection, values) ?: continue
            context.contentResolver.openOutputStream(uri)?.use { out ->
                file.inputStream().use { it.copyTo(out) }
            }
            count++
        }
        return count
    }
}
