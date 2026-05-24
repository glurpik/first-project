package com.cryptominer.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class MiningService : Service() {

    companion object {
        private const val TAG = "MiningService"
        const val NOTIFICATION_ID = 1001
        const val CHANNEL_ID = "mining_channel"
        const val STATS_UPDATE_INTERVAL_MS = 2000L
    }

    private val binder = LocalBinder()
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var stratumClient: StratumClient? = null
    private var miningWorker: MiningWorker? = null
    private var statsManager: StatsManager? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private var isMiningActive = false
    private var statsUpdateJob: Job? = null

    inner class LocalBinder : Binder() {
        fun getService(): MiningService = this@MiningService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "MiningService created")
        createNotificationChannel()
        acquireWakeLock()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "MiningService onStartCommand")

        val wallet = intent?.getStringExtra("wallet") ?: return START_NOT_STICKY
        val worker = intent.getStringExtra("worker") ?: "worker1"
        val host = intent.getStringExtra("host") ?: "pool.supportxmr.com"
        val port = intent.getIntExtra("port", 3333)

        // Start foreground immediately
        startForeground(NOTIFICATION_ID, buildNotification("Starting miner...", 0.0))

        // Initialize components
        statsManager = StatsManager(applicationContext)
        statsManager?.reset()

        miningWorker = MiningWorker(statsManager!!)

        stratumClient = StratumClient(
            host = host,
            port = port,
            wallet = wallet,
            worker = worker,
            statsManager = statsManager!!,
            onJobReceived = { job ->
                Log.d(TAG, "New job received: ${job.jobId}")
                miningWorker?.submitJob(job)
            },
            onShareAccepted = {
                Log.d(TAG, "Share accepted!")
                statsManager?.incrementAccepted()
                broadcastStats("Mining - Share accepted!")
            },
            onShareRejected = { reason ->
                Log.w(TAG, "Share rejected: $reason")
                statsManager?.incrementRejected()
                broadcastStats("Share rejected: $reason")
            },
            onStatusChange = { status ->
                Log.d(TAG, "Status: $status")
                broadcastStats(status)
            },
            onShareReady = { shareData ->
                stratumClient?.submitShare(shareData)
            }
        )

        isMiningActive = true

        // Start mining in background
        serviceScope.launch {
            try {
                stratumClient?.connect()
                startMiningLoop()
            } catch (e: Exception) {
                Log.e(TAG, "Mining error: ${e.message}", e)
                broadcastStats("Error: ${e.message}")
            }
        }

        // Start periodic stats updates
        startStatsUpdates()

        return START_STICKY
    }

    private suspend fun startMiningLoop() {
        while (isMiningActive && serviceScope.isActive) {
            miningWorker?.mineOneIteration()
            delay(1) // Yield to allow coroutine cancellation
        }
    }

    private fun startStatsUpdates() {
        statsUpdateJob = serviceScope.launch {
            while (isActive && isMiningActive) {
                val stats = statsManager?.getStats()
                val hashrate = miningWorker?.getHashrate() ?: 0.0
                val status = if (stratumClient?.isConnected() == true) "Mining..." else "Connecting..."

                // Update notification
                updateNotification(status, hashrate)

                // Save stats to file
                statsManager?.saveToFile(hashrate)

                // Broadcast to UI
                broadcastStats(status, hashrate)

                delay(STATS_UPDATE_INTERVAL_MS)
            }
        }
    }

    private fun broadcastStats(status: String, hashrate: Double? = null) {
        val stats = statsManager?.getStats() ?: return
        val actualHashrate = hashrate ?: miningWorker?.getHashrate() ?: 0.0

        val intent = Intent(MainActivity.ACTION_STATS_UPDATE).apply {
            putExtra(MainActivity.EXTRA_HASHRATE, actualHashrate)
            putExtra(MainActivity.EXTRA_ACCEPTED, stats.accepted)
            putExtra(MainActivity.EXTRA_REJECTED, stats.rejected)
            putExtra(MainActivity.EXTRA_TOTAL_HASHES, stats.totalHashes)
            putExtra(MainActivity.EXTRA_UPTIME, stats.uptimeSeconds)
            putExtra(MainActivity.EXTRA_STATUS, status)
        }
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun updateNotification(status: String, hashrate: Double) {
        val notification = buildNotification(status, hashrate)
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, notification)
    }

    private fun buildNotification(status: String, hashrate: Double): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val hashrateText = when {
            hashrate >= 1_000 -> String.format("%.2f KH/s", hashrate / 1_000)
            else -> String.format("%.2f H/s", hashrate)
        }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("XMR Miner Active")
            .setContentText("$status | $hashrateText")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Mining Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows mining status and hashrate"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun acquireWakeLock() {
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "CryptoMiner::MiningWakeLock"
        ).apply {
            acquire(24 * 60 * 60 * 1000L) // 24 hours max
        }
    }

    fun stopMining() {
        Log.d(TAG, "Stopping mining")
        isMiningActive = false
        statsUpdateJob?.cancel()
        miningWorker?.stop()
        stratumClient?.disconnect()
        broadcastStats("Stopped", 0.0)
    }

    fun isMining(): Boolean = isMiningActive

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "MiningService destroyed")
        stopMining()
        serviceScope.cancel()
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
    }
}
