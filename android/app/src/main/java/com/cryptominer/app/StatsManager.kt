package com.cryptominer.app

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class StatsManager(private val context: Context) {

    companion object {
        private const val TAG = "StatsManager"
        private const val STATS_FILE = "mining_stats.json"
    }

    private val acceptedShares = AtomicInteger(0)
    private val rejectedShares = AtomicInteger(0)
    private val totalHashes = AtomicLong(0)
    private var startTime = System.currentTimeMillis()

    @Volatile private var difficulty = 1.0

    data class MiningStats(
        val accepted: Int,
        val rejected: Int,
        val totalHashes: Long,
        val uptimeSeconds: Long,
        val difficulty: Double
    )

    fun reset() {
        acceptedShares.set(0)
        rejectedShares.set(0)
        totalHashes.set(0)
        startTime = System.currentTimeMillis()
        difficulty = 1.0
    }

    fun incrementAccepted() = acceptedShares.incrementAndGet()
    fun incrementRejected() = rejectedShares.incrementAndGet()
    fun incrementTotalHashes() = totalHashes.incrementAndGet()

    fun setDifficulty(d: Double) {
        difficulty = d
    }

    fun getDifficulty(): Double = difficulty

    fun getStats(): MiningStats {
        val uptimeMs = System.currentTimeMillis() - startTime
        return MiningStats(
            accepted = acceptedShares.get(),
            rejected = rejectedShares.get(),
            totalHashes = totalHashes.get(),
            uptimeSeconds = uptimeMs / 1000,
            difficulty = difficulty
        )
    }

    fun saveToFile(hashrate: Double) {
        try {
            val stats = getStats()
            val json = JSONObject().apply {
                put("hashrate", hashrate)
                put("accepted", stats.accepted)
                put("rejected", stats.rejected)
                put("total_hashes", stats.totalHashes)
                put("uptime_seconds", stats.uptimeSeconds)
                put("difficulty", stats.difficulty)
                put("timestamp", System.currentTimeMillis())
                val total = stats.accepted + stats.rejected
                put("efficiency", if (total > 0) stats.accepted.toDouble() / total * 100 else 0.0)
            }

            val file = File(context.getExternalFilesDir(null), STATS_FILE)
            file.writeText(json.toString(2))
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save stats: ${e.message}")
        }
    }
}
