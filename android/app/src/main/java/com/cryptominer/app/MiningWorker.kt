package com.cryptominer.app

import android.util.Log
import java.security.MessageDigest
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

class MiningWorker(private val statsManager: StatsManager) {

    companion object {
        private const val TAG = "MiningWorker"
    }

    private val running = AtomicBoolean(true)
    private val hashCount = AtomicLong(0)
    private val jobQueue = ArrayBlockingQueue<MiningJob>(4)

    private var currentJob: MiningJob? = null
    private var currentNonce: Long = 0
    private var currentExtraNonce2: Long = 0

    private var lastHashrateTime = System.currentTimeMillis()
    private var lastHashCount = 0L
    private var currentHashrate = 0.0

    private val md = MessageDigest.getInstance("SHA-256")

    fun submitJob(job: MiningJob) {
        currentJob = job
        currentNonce = 0
        currentExtraNonce2 = 0
        Log.d(TAG, "New job accepted: ${job.jobId}")
    }

    fun mineOneIteration() {
        val job = currentJob ?: return
        if (!running.get()) return

        val extraNonce2 = currentExtraNonce2.toHex(job.extraNonce2Size * 2)
        val header = buildBlockHeader(job, extraNonce2, currentNonce)

        val hash = doubleHash(header)
        hashCount.incrementAndGet()
        statsManager.incrementTotalHashes()

        // Check if hash meets target (simplified: check leading zeros)
        val difficulty = statsManager.getDifficulty()
        if (meetsTarget(hash, difficulty)) {
            Log.d(TAG, "Found share! nonce=$currentNonce")
            // In a real implementation, submit to pool
        }

        currentNonce++
        if (currentNonce > 0xFFFFFFFFL) {
            currentNonce = 0
            currentExtraNonce2++
        }

        updateHashrate()
    }

    private fun buildBlockHeader(job: MiningJob, extraNonce2: String, nonce: Long): ByteArray {
        val sb = StringBuilder()
        sb.append(job.coinbase1)
        sb.append(job.extraNonce1)
        sb.append(extraNonce2)
        sb.append(job.coinbase2)

        var merkleRoot = hash256Hex(hexToBytes(sb.toString()))
        for (branch in job.merkleBranches) {
            merkleRoot = hash256Hex(hexToBytes(merkleRoot + branch))
        }

        val header = StringBuilder()
        header.append(job.blockVersion)
        header.append(job.prevHash)
        header.append(merkleRoot)
        header.append(job.nTime)
        header.append(job.nBits)
        header.append(nonce.toHex(8))

        return hexToBytes(header.toString())
    }

    private fun meetsTarget(hash: ByteArray, difficulty: Double): Boolean {
        val leadingZeros = (difficulty / 65536).toInt().coerceAtLeast(1)
        for (i in 0 until minOf(leadingZeros / 2, hash.size)) {
            if (hash[i] != 0.toByte()) return false
        }
        return leadingZeros > 0
    }

    private fun doubleHash(data: ByteArray): ByteArray {
        return md.digest(md.digest(data))
    }

    private fun hash256Hex(data: ByteArray): String {
        return doubleHash(data).toHexString()
    }

    private fun updateHashrate() {
        val now = System.currentTimeMillis()
        val elapsed = now - lastHashrateTime
        if (elapsed >= 1000) {
            val count = hashCount.get()
            currentHashrate = (count - lastHashCount).toDouble() / (elapsed / 1000.0)
            lastHashCount = count
            lastHashrateTime = now
        }
    }

    fun getHashrate(): Double = currentHashrate

    fun stop() {
        running.set(false)
        currentJob = null
    }

    private fun Long.toHex(length: Int): String {
        return String.format("%0${length}x", this)
    }

    private fun ByteArray.toHexString(): String {
        return joinToString("") { "%02x".format(it) }
    }

    private fun hexToBytes(hex: String): ByteArray {
        val cleanHex = if (hex.length % 2 != 0) "0$hex" else hex
        return ByteArray(cleanHex.length / 2) { i ->
            cleanHex.substring(i * 2, i * 2 + 2).toInt(16).toByte()
        }
    }
}
