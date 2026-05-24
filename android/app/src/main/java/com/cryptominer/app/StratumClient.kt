package com.cryptominer.app

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Stratum protocol client for XMR pool mining.
 * Implements: mining.subscribe, mining.authorize, mining.submit
 *
 * Stratum protocol flow:
 * 1. Client connects to pool server
 * 2. Client sends mining.subscribe
 * 3. Server responds with subscription details + extranonce1, extranonce2_size
 * 4. Client sends mining.authorize with wallet address
 * 5. Server sends mining.notify with job details
 * 6. Client mines and sends mining.submit with nonce
 */
class StratumClient(
    private val host: String,
    private val port: Int,
    private val wallet: String,
    private val worker: String,
    private val statsManager: StatsManager,
    private val onJobReceived: (MiningJob) -> Unit,
    private val onShareAccepted: () -> Unit,
    private val onShareRejected: (String) -> Unit,
    private val onStatusChange: (String) -> Unit,
    private val onShareReady: (ShareData) -> Unit
) {

    companion object {
        private const val TAG = "StratumClient"
        private const val SOCKET_TIMEOUT_MS = 30_000
        private const val RECONNECT_DELAY_MS = 5_000L
        private const val KEEPALIVE_INTERVAL_MS = 30_000L
    }

    private var socket: Socket? = null
    private var writer: PrintWriter? = null
    private var reader: BufferedReader? = null

    private val messageId = AtomicInteger(1)
    private val connected = AtomicBoolean(false)
    private val authorized = AtomicBoolean(false)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // Subscription data
    private var subscriptionId: String = ""
    private var extraNonce1: String = ""
    private var extraNonce2Size: Int = 4

    // Current job
    private var currentJob: MiningJob? = null

    // Pending request IDs
    private val pendingSubscribeId = 1
    private val pendingAuthorizeId = 2

    suspend fun connect() {
        var retryCount = 0
        while (scope.isActive) {
            try {
                onStatusChange("Connecting to $host:$port...")
                Log.d(TAG, "Connecting to $host:$port")

                socket = Socket(host, port).apply {
                    soTimeout = SOCKET_TIMEOUT_MS
                    keepAlive = true
                    tcpNoDelay = true
                }

                writer = PrintWriter(socket!!.getOutputStream(), true)
                reader = BufferedReader(InputStreamReader(socket!!.getInputStream()))
                connected.set(true)
                retryCount = 0

                onStatusChange("Connected. Subscribing...")
                Log.d(TAG, "Connected to pool")

                // Send subscribe
                sendSubscribe()

                // Start reading loop
                readLoop()

            } catch (e: SocketTimeoutException) {
                Log.w(TAG, "Socket timeout: ${e.message}")
                handleDisconnect("Timeout - reconnecting...")
            } catch (e: Exception) {
                Log.e(TAG, "Connection error: ${e.message}", e)
                retryCount++
                val delay = minOf(RECONNECT_DELAY_MS * retryCount, 60_000L)
                onStatusChange("Connection failed. Retrying in ${delay / 1000}s...")
                handleDisconnect("Error: ${e.message}")
                delay(delay)
            }
        }
    }

    private fun sendSubscribe() {
        val request = JSONObject().apply {
            put("id", pendingSubscribeId)
            put("method", "mining.subscribe")
            put("params", JSONArray().apply {
                put("CryptoMinerAndroid/1.0.0")
            })
        }
        sendMessage(request.toString())
        Log.d(TAG, "Sent mining.subscribe")
    }

    private fun sendAuthorize() {
        val login = "$wallet.$worker"
        val request = JSONObject().apply {
            put("id", pendingAuthorizeId)
            put("method", "mining.authorize")
            put("params", JSONArray().apply {
                put(login)
                put("x") // password (any value works for most pools)
            })
        }
        sendMessage(request.toString())
        Log.d(TAG, "Sent mining.authorize for $login")
        onStatusChange("Authorizing...")
    }

    fun submitShare(shareData: ShareData) {
        if (!connected.get() || !authorized.get()) {
            Log.w(TAG, "Cannot submit share: not connected/authorized")
            return
        }

        val id = messageId.getAndIncrement()
        val request = JSONObject().apply {
            put("id", id)
            put("method", "mining.submit")
            put("params", JSONArray().apply {
                put("$wallet.$worker")  // worker name
                put(shareData.jobId)    // job id
                put(shareData.extraNonce2) // extranonce2
                put(shareData.nTime)    // ntime
                put(shareData.nonce)    // nonce
            })
        }
        sendMessage(request.toString())
        Log.d(TAG, "Submitted share for job ${shareData.jobId}")
    }

    private fun sendKeepalive() {
        val request = JSONObject().apply {
            put("id", messageId.getAndIncrement())
            put("method", "mining.get_transactions")
            put("params", JSONArray())
        }
        sendMessage(request.toString())
    }

    private suspend fun readLoop() {
        // Start keepalive
        scope.launch {
            while (connected.get() && scope.isActive) {
                delay(KEEPALIVE_INTERVAL_MS)
                if (connected.get()) {
                    try {
                        sendKeepalive()
                    } catch (e: Exception) {
                        Log.w(TAG, "Keepalive failed: ${e.message}")
                    }
                }
            }
        }

        // Read messages
        try {
            var line: String?
            while (connected.get()) {
                line = reader?.readLine()
                if (line == null) {
                    Log.w(TAG, "Connection closed by server")
                    break
                }
                if (line.isNotBlank()) {
                    processMessage(line)
                }
            }
        } catch (e: Exception) {
            if (connected.get()) {
                Log.e(TAG, "Read error: ${e.message}")
            }
        }

        handleDisconnect("Disconnected from pool")
    }

    private fun processMessage(raw: String) {
        Log.v(TAG, "RX: $raw")
        try {
            val json = JSONObject(raw)

            // Check if it's a response (has "id") or notification (no "id" or id=null)
            val id = if (json.has("id") && !json.isNull("id")) json.getInt("id") else -1
            val method = if (json.has("method") && !json.isNull("method")) json.getString("method") else ""
            val result = if (json.has("result")) json.get("result") else null
            val error = if (json.has("error") && !json.isNull("error")) json.get("error") else null

            when {
                // Handle responses to our requests
                id == pendingSubscribeId && result != null -> handleSubscribeResponse(json)
                id == pendingAuthorizeId && result != null -> handleAuthorizeResponse(json)
                id > pendingAuthorizeId && error != null -> handleShareRejected(json)
                id > pendingAuthorizeId && result != null -> handleShareAccepted(json)

                // Handle server notifications
                method == "mining.notify" -> handleMiningNotify(json)
                method == "mining.set_difficulty" -> handleSetDifficulty(json)
                method == "mining.set_extranonce" -> handleSetExtranonce(json)
                method == "client.show_message" -> handleShowMessage(json)

                else -> Log.d(TAG, "Unhandled message: $raw")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse message: $raw", e)
        }
    }

    private fun handleSubscribeResponse(json: JSONObject) {
        Log.d(TAG, "Subscribe response: $json")
        try {
            val result = json.getJSONArray("result")

            // result[0] = subscription details array
            // result[1] = extranonce1 (hex string)
            // result[2] = extranonce2 size
            if (!result.isNull(1)) {
                extraNonce1 = result.getString(1)
            }
            if (!result.isNull(2)) {
                extraNonce2Size = result.getInt(2)
            }

            Log.d(TAG, "Subscribed. extranonce1=$extraNonce1, extranonce2_size=$extraNonce2Size")
            sendAuthorize()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse subscribe response: ${e.message}")
            sendAuthorize() // Try to authorize anyway
        }
    }

    private fun handleAuthorizeResponse(json: JSONObject) {
        val error = if (json.has("error") && !json.isNull("error")) json.get("error") else null
        val result = if (json.has("result")) json.get("result") else null

        if (error != null) {
            Log.e(TAG, "Authorization failed: $error")
            onStatusChange("Auth failed: $error")
        } else if (result == true || result.toString() == "true") {
            authorized.set(true)
            Log.d(TAG, "Authorized successfully")
            onStatusChange("Authorized. Waiting for work...")
        } else {
            Log.w(TAG, "Unexpected auth response: $result")
            onStatusChange("Auth response: $result")
        }
    }

    private fun handleMiningNotify(json: JSONObject) {
        try {
            val params = json.getJSONArray("params")
            val job = MiningJob(
                jobId = params.getString(0),
                prevHash = params.getString(1),
                coinbase1 = params.getString(2),
                coinbase2 = params.getString(3),
                merkleBranches = parseMerkleBranches(params.getJSONArray(4)),
                blockVersion = params.getString(5),
                nBits = params.getString(6),
                nTime = params.getString(7),
                cleanJobs = params.getBoolean(8),
                extraNonce1 = extraNonce1,
                extraNonce2Size = extraNonce2Size
            )
            currentJob = job
            Log.d(TAG, "New job: ${job.jobId}")
            onJobReceived(job)
            if (authorized.get()) {
                onStatusChange("Mining job ${job.jobId.take(8)}...")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse mining.notify: ${e.message}")
        }
    }

    private fun parseMerkleBranches(arr: JSONArray): List<String> {
        val branches = mutableListOf<String>()
        for (i in 0 until arr.length()) {
            branches.add(arr.getString(i))
        }
        return branches
    }

    private fun handleSetDifficulty(json: JSONObject) {
        try {
            val difficulty = json.getJSONArray("params").getDouble(0)
            Log.d(TAG, "New difficulty: $difficulty")
            statsManager.setDifficulty(difficulty)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse set_difficulty: ${e.message}")
        }
    }

    private fun handleSetExtranonce(json: JSONObject) {
        try {
            val params = json.getJSONArray("params")
            extraNonce1 = params.getString(0)
            extraNonce2Size = params.getInt(1)
            Log.d(TAG, "New extranonce1=$extraNonce1, size=$extraNonce2Size")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse set_extranonce: ${e.message}")
        }
    }

    private fun handleShowMessage(json: JSONObject) {
        try {
            val msg = json.getJSONArray("params").getString(0)
            Log.d(TAG, "Pool message: $msg")
            onStatusChange("Pool: $msg")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse show_message: ${e.message}")
        }
    }

    private fun handleShareAccepted(json: JSONObject) {
        Log.d(TAG, "Share accepted: $json")
        onShareAccepted()
    }

    private fun handleShareRejected(json: JSONObject) {
        val error = json.optString("error", "Unknown reason")
        Log.w(TAG, "Share rejected: $error")
        onShareRejected(error)
    }

    private fun sendMessage(message: String) {
        try {
            Log.v(TAG, "TX: $message")
            writer?.println(message)
            writer?.flush()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send message: ${e.message}")
        }
    }

    private fun handleDisconnect(reason: String) {
        connected.set(false)
        authorized.set(false)
        try {
            writer?.close()
            reader?.close()
            socket?.close()
        } catch (e: Exception) {
            // Ignore cleanup errors
        }
        writer = null
        reader = null
        socket = null
        onStatusChange(reason)
    }

    fun disconnect() {
        handleDisconnect("Disconnected")
        scope.isActive.let { }
    }

    fun isConnected(): Boolean = connected.get()
    fun isAuthorized(): Boolean = authorized.get()
    fun getCurrentJob(): MiningJob? = currentJob
}

/**
 * Represents a mining job received from the pool via mining.notify
 */
data class MiningJob(
    val jobId: String,
    val prevHash: String,
    val coinbase1: String,
    val coinbase2: String,
    val merkleBranches: List<String>,
    val blockVersion: String,
    val nBits: String,
    val nTime: String,
    val cleanJobs: Boolean,
    val extraNonce1: String,
    val extraNonce2Size: Int
)

/**
 * Share data to submit back to the pool
 */
data class ShareData(
    val jobId: String,
    val extraNonce2: String,
    val nTime: String,
    val nonce: String
)
