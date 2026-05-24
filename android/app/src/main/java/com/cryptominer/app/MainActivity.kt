package com.cryptominer.app

import android.Manifest
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.google.android.material.card.MaterialCardView
import com.google.android.material.switchmaterial.SwitchMaterial
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    companion object {
        const val ACTION_STATS_UPDATE = "com.cryptominer.STATS_UPDATE"
        const val EXTRA_HASHRATE = "hashrate"
        const val EXTRA_ACCEPTED = "accepted"
        const val EXTRA_REJECTED = "rejected"
        const val EXTRA_TOTAL_HASHES = "total_hashes"
        const val EXTRA_UPTIME = "uptime"
        const val EXTRA_STATUS = "status"
        const val PREF_WALLET = "wallet_address"
        const val PREF_WORKER = "worker_name"
        const val PREF_POOL_HOST = "pool_host"
        const val PREF_POOL_PORT = "pool_port"
        const val REQUEST_NOTIFICATION_PERMISSION = 1001
    }

    private var miningService: MiningService? = null
    private var isBound = false

    // UI components
    private lateinit var etWalletAddress: EditText
    private lateinit var etWorkerName: EditText
    private lateinit var etPoolHost: EditText
    private lateinit var etPoolPort: EditText
    private lateinit var btnStartStop: Button
    private lateinit var tvHashrate: TextView
    private lateinit var tvAccepted: TextView
    private lateinit var tvRejected: TextView
    private lateinit var tvTotalHashes: TextView
    private lateinit var tvUptime: TextView
    private lateinit var tvStatus: TextView
    private lateinit var tvEfficiency: TextView
    private lateinit var progressMining: ProgressBar
    private lateinit var cardStats: MaterialCardView
    private lateinit var layoutSettings: LinearLayout

    private val statsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ACTION_STATS_UPDATE) {
                updateUI(intent)
            }
        }
    }

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            val binder = service as MiningService.LocalBinder
            miningService = binder.getService()
            isBound = true
            updateMiningButtonState(miningService?.isMining() == true)
        }

        override fun onServiceDisconnected(name: ComponentName) {
            miningService = null
            isBound = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        loadPreferences()
        setupListeners()
        requestNotificationPermission()

        // Register broadcast receiver for stats updates
        val filter = IntentFilter(ACTION_STATS_UPDATE)
        LocalBroadcastManager.getInstance(this).registerReceiver(statsReceiver, filter)

        // Bind to service if already running
        val intent = Intent(this, MiningService::class.java)
        bindService(intent, serviceConnection, 0)
    }

    private fun initViews() {
        etWalletAddress = findViewById(R.id.et_wallet_address)
        etWorkerName = findViewById(R.id.et_worker_name)
        etPoolHost = findViewById(R.id.et_pool_host)
        etPoolPort = findViewById(R.id.et_pool_port)
        btnStartStop = findViewById(R.id.btn_start_stop)
        tvHashrate = findViewById(R.id.tv_hashrate)
        tvAccepted = findViewById(R.id.tv_accepted)
        tvRejected = findViewById(R.id.tv_rejected)
        tvTotalHashes = findViewById(R.id.tv_total_hashes)
        tvUptime = findViewById(R.id.tv_uptime)
        tvStatus = findViewById(R.id.tv_status)
        tvEfficiency = findViewById(R.id.tv_efficiency)
        progressMining = findViewById(R.id.progress_mining)
        cardStats = findViewById(R.id.card_stats)
        layoutSettings = findViewById(R.id.layout_settings)
    }

    private fun loadPreferences() {
        val prefs = getSharedPreferences("miner_prefs", Context.MODE_PRIVATE)
        etWalletAddress.setText(prefs.getString(PREF_WALLET, ""))
        etWorkerName.setText(prefs.getString(PREF_WORKER, "worker1"))
        etPoolHost.setText(prefs.getString(PREF_POOL_HOST, "pool.supportxmr.com"))
        etPoolPort.setText(prefs.getString(PREF_POOL_PORT, "3333"))
    }

    private fun savePreferences() {
        val prefs = getSharedPreferences("miner_prefs", Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString(PREF_WALLET, etWalletAddress.text.toString().trim())
            putString(PREF_WORKER, etWorkerName.text.toString().trim())
            putString(PREF_POOL_HOST, etPoolHost.text.toString().trim())
            putString(PREF_POOL_PORT, etPoolPort.text.toString().trim())
            apply()
        }
    }

    private fun setupListeners() {
        btnStartStop.setOnClickListener {
            if (miningService?.isMining() == true) {
                stopMining()
            } else {
                startMining()
            }
        }
    }

    private fun startMining() {
        val wallet = etWalletAddress.text.toString().trim()
        val worker = etWorkerName.text.toString().trim().ifEmpty { "worker1" }
        val host = etPoolHost.text.toString().trim().ifEmpty { "pool.supportxmr.com" }
        val portStr = etPoolPort.text.toString().trim().ifEmpty { "3333" }
        val port = portStr.toIntOrNull() ?: 3333

        if (wallet.isEmpty()) {
            Toast.makeText(this, "Please enter your XMR wallet address", Toast.LENGTH_LONG).show()
            etWalletAddress.requestFocus()
            return
        }

        if (wallet.length < 95) {
            Toast.makeText(this, "Invalid wallet address (too short)", Toast.LENGTH_LONG).show()
            return
        }

        savePreferences()

        val serviceIntent = Intent(this, MiningService::class.java).apply {
            putExtra("wallet", wallet)
            putExtra("worker", worker)
            putExtra("host", host)
            putExtra("port", port)
        }

        ContextCompat.startForegroundService(this, serviceIntent)

        if (!isBound) {
            bindService(serviceIntent, serviceConnection, 0)
        }

        updateMiningButtonState(true)
        layoutSettings.visibility = View.GONE
        cardStats.visibility = View.VISIBLE
        tvStatus.text = "Connecting to pool..."
        progressMining.visibility = View.VISIBLE
    }

    private fun stopMining() {
        miningService?.stopMining()
        val serviceIntent = Intent(this, MiningService::class.java)
        stopService(serviceIntent)
        updateMiningButtonState(false)
        layoutSettings.visibility = View.VISIBLE
        tvStatus.text = "Stopped"
        progressMining.visibility = View.GONE
    }

    private fun updateMiningButtonState(isMining: Boolean) {
        if (isMining) {
            btnStartStop.text = getString(R.string.stop_mining)
            btnStartStop.setBackgroundColor(ContextCompat.getColor(this, R.color.stop_color))
        } else {
            btnStartStop.text = getString(R.string.start_mining)
            btnStartStop.setBackgroundColor(ContextCompat.getColor(this, R.color.start_color))
            cardStats.visibility = View.GONE
            progressMining.visibility = View.GONE
        }
    }

    private fun updateUI(intent: Intent) {
        val hashrate = intent.getDoubleExtra(EXTRA_HASHRATE, 0.0)
        val accepted = intent.getIntExtra(EXTRA_ACCEPTED, 0)
        val rejected = intent.getIntExtra(EXTRA_REJECTED, 0)
        val totalHashes = intent.getLongExtra(EXTRA_TOTAL_HASHES, 0L)
        val uptime = intent.getLongExtra(EXTRA_UPTIME, 0L)
        val status = intent.getStringExtra(EXTRA_STATUS) ?: ""

        tvHashrate.text = formatHashrate(hashrate)
        tvAccepted.text = accepted.toString()
        tvRejected.text = rejected.toString()
        tvTotalHashes.text = formatNumber(totalHashes)
        tvUptime.text = formatUptime(uptime)
        tvStatus.text = status

        val total = accepted + rejected
        val efficiency = if (total > 0) (accepted.toFloat() / total * 100).toInt() else 0
        tvEfficiency.text = "$efficiency%"

        if (status.contains("Mining", ignoreCase = true) || status.contains("Authorized", ignoreCase = true)) {
            progressMining.visibility = View.GONE
            cardStats.visibility = View.VISIBLE
        }

        if (status.contains("Error", ignoreCase = true) || status.contains("Failed", ignoreCase = true)) {
            tvStatus.setTextColor(ContextCompat.getColor(this, R.color.error_color))
        } else {
            tvStatus.setTextColor(ContextCompat.getColor(this, R.color.status_ok_color))
        }
    }

    private fun formatHashrate(hps: Double): String {
        return when {
            hps >= 1_000_000 -> String.format("%.2f MH/s", hps / 1_000_000)
            hps >= 1_000 -> String.format("%.2f KH/s", hps / 1_000)
            else -> String.format("%.2f H/s", hps)
        }
    }

    private fun formatNumber(n: Long): String {
        return when {
            n >= 1_000_000_000L -> String.format("%.2fG", n / 1_000_000_000.0)
            n >= 1_000_000L -> String.format("%.2fM", n / 1_000_000.0)
            n >= 1_000L -> String.format("%.2fK", n / 1_000.0)
            else -> n.toString()
        }
    }

    private fun formatUptime(seconds: Long): String {
        val h = seconds / 3600
        val m = (seconds % 3600) / 60
        val s = seconds % 60
        return String.format("%02d:%02d:%02d", h, m, s)
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    REQUEST_NOTIFICATION_PERMISSION
                )
            }
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_NOTIFICATION_PERMISSION) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                Toast.makeText(this, "Notification permission granted", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        LocalBroadcastManager.getInstance(this).unregisterReceiver(statsReceiver)
        if (isBound) {
            unbindService(serviceConnection)
            isBound = false
        }
    }
}
