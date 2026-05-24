/**
 * server.js — XMR Miner Stats API + Dashboard Server
 *
 * Endpoints:
 *   GET  /           → Serves the web dashboard (../dashboard/index.html)
 *   GET  /api/stats  → Returns current mining stats as JSON
 *   POST /api/stats  → Receives stats from the Android app; stores in memory + file
 *   GET  /api/health → Health check
 *
 * Usage:
 *   npm install
 *   npm start        # production
 *   npm run dev      # with file watching (Node 18+)
 */

'use strict';

const express  = require('express');
const cors     = require('cors');
const path     = require('path');
const fs       = require('fs');
const http     = require('http');

const app  = express();
const PORT = process.env.PORT || 3000;

/* ============================================================
   Middleware
============================================================ */
app.use(cors({
    origin: '*',
    methods: ['GET', 'POST', 'OPTIONS'],
}));
app.use(express.json({ limit: '64kb' }));
app.use(express.urlencoded({ extended: true }));

// Request logging
app.use((req, _res, next) => {
    const ts = new Date().toISOString();
    console.log(`[${ts}] ${req.method} ${req.path}`);
    next();
});

/* ============================================================
   In-memory stats store
============================================================ */
const DEFAULT_STATS = {
    hashrate:       0,
    accepted:       0,
    rejected:       0,
    total_hashes:   0,
    uptime_seconds: 0,
    difficulty:     1,
    efficiency:     0,
    worker:         null,
    wallet:         null,
    pool:           'pool.supportxmr.com:3333',
    timestamp:      null,
    online:         false,
};

let currentStats = { ...DEFAULT_STATS };

// Path to persist stats to disk (optional)
const STATS_FILE = path.join(__dirname, 'mining_stats.json');

/* ============================================================
   Load persisted stats on startup
============================================================ */
function loadPersistedStats() {
    try {
        if (fs.existsSync(STATS_FILE)) {
            const raw  = fs.readFileSync(STATS_FILE, 'utf8');
            const data = JSON.parse(raw);
            currentStats = { ...DEFAULT_STATS, ...data };
            console.log('[server] Loaded persisted stats from', STATS_FILE);
        }
    } catch (err) {
        console.warn('[server] Could not load persisted stats:', err.message);
    }
}

/* ============================================================
   Mark miner offline if no update received for > 30 seconds
============================================================ */
const OFFLINE_TIMEOUT_MS = 30_000;

function checkOnlineStatus() {
    if (!currentStats.timestamp) {
        currentStats.online = false;
        return;
    }
    const age = Date.now() - new Date(currentStats.timestamp).getTime();
    currentStats.online = age < OFFLINE_TIMEOUT_MS;
}

setInterval(checkOnlineStatus, 5_000);

/* ============================================================
   Routes
============================================================ */

/**
 * GET /api/health — Simple health check
 */
app.get('/api/health', (_req, res) => {
    res.json({
        status:    'ok',
        uptime:    process.uptime(),
        timestamp: new Date().toISOString(),
    });
});

/**
 * GET /api/stats — Return current mining stats
 */
app.get('/api/stats', (_req, res) => {
    checkOnlineStatus();
    res.json(currentStats);
});

/**
 * POST /api/stats — Receive stats update from Android app
 *
 * Expected JSON body:
 * {
 *   "hashrate":       <number>,
 *   "accepted":       <number>,
 *   "rejected":       <number>,
 *   "total_hashes":   <number>,
 *   "uptime_seconds": <number>,
 *   "difficulty":     <number>,
 *   "worker":         <string>,  // optional
 *   "wallet":         <string>,  // optional
 *   "pool":           <string>   // optional
 * }
 */
app.post('/api/stats', (req, res) => {
    const body = req.body;

    if (!body || typeof body !== 'object') {
        return res.status(400).json({ error: 'Invalid request body' });
    }

    // Validate required numeric fields
    const numericFields = ['hashrate', 'accepted', 'rejected', 'total_hashes', 'uptime_seconds'];
    for (const field of numericFields) {
        if (body[field] !== undefined && typeof body[field] !== 'number') {
            return res.status(400).json({ error: `Field "${field}" must be a number` });
        }
    }

    // Merge incoming data
    currentStats = {
        hashrate:       typeof body.hashrate       === 'number' ? body.hashrate       : currentStats.hashrate,
        accepted:       typeof body.accepted       === 'number' ? body.accepted       : currentStats.accepted,
        rejected:       typeof body.rejected       === 'number' ? body.rejected       : currentStats.rejected,
        total_hashes:   typeof body.total_hashes   === 'number' ? body.total_hashes   : currentStats.total_hashes,
        uptime_seconds: typeof body.uptime_seconds === 'number' ? body.uptime_seconds : currentStats.uptime_seconds,
        difficulty:     typeof body.difficulty     === 'number' ? body.difficulty     : currentStats.difficulty,
        worker:         typeof body.worker         === 'string' ? body.worker         : currentStats.worker,
        wallet:         typeof body.wallet         === 'string' ? body.wallet         : currentStats.wallet,
        pool:           typeof body.pool           === 'string' ? body.pool           : currentStats.pool,
        timestamp:      new Date().toISOString(),
        online:         true,
    };

    // Derive efficiency
    const total = currentStats.accepted + currentStats.rejected;
    currentStats.efficiency = total > 0
        ? parseFloat(((currentStats.accepted / total) * 100).toFixed(2))
        : 0;

    // Persist to file (non-blocking)
    persistStats();

    console.log(`[server] Stats update: ${currentStats.hashrate.toFixed(2)} H/s | acc=${currentStats.accepted} | rej=${currentStats.rejected}`);

    res.json({ status: 'ok', received: currentStats.timestamp });
});

/**
 * Serve the web dashboard
 * Static files: /dashboard/  (served from ../dashboard/)
 */
const dashboardDir = path.join(__dirname, '..', 'dashboard');

if (fs.existsSync(dashboardDir)) {
    app.use(express.static(dashboardDir));
    app.get('/', (_req, res) => {
        res.sendFile(path.join(dashboardDir, 'index.html'));
    });
    console.log('[server] Serving dashboard from', dashboardDir);
} else {
    app.get('/', (_req, res) => {
        res.send(`
            <html><body style="font-family:monospace;background:#111;color:#eee;padding:2rem">
            <h2 style="color:#FF6D00">XMR Miner Stats Server</h2>
            <p>Dashboard directory not found at <code>${dashboardDir}</code></p>
            <p>API is running. Try <a href="/api/stats" style="color:#FF6D00">/api/stats</a></p>
            </body></html>
        `);
    });
}

/* ============================================================
   Persist stats to disk
============================================================ */
function persistStats() {
    const json = JSON.stringify(currentStats, null, 2);
    fs.writeFile(STATS_FILE, json, err => {
        if (err) console.warn('[server] Failed to persist stats:', err.message);
    });
}

/* ============================================================
   Start server
============================================================ */
loadPersistedStats();

const server = http.createServer(app);

server.listen(PORT, '0.0.0.0', () => {
    console.log('');
    console.log('  ╔══════════════════════════════════════╗');
    console.log('  ║     XMR Miner Stats Server v1.0      ║');
    console.log('  ╠══════════════════════════════════════╣');
    console.log(`  ║  Dashboard : http://localhost:${PORT}     ║`);
    console.log(`  ║  API       : http://localhost:${PORT}/api ║`);
    console.log('  ╚══════════════════════════════════════╝');
    console.log('');
});

server.on('error', err => {
    if (err.code === 'EADDRINUSE') {
        console.error(`[server] Port ${PORT} is already in use. Set PORT env var to use a different port.`);
    } else {
        console.error('[server] Server error:', err);
    }
    process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('[server] SIGTERM received, shutting down gracefully...');
    server.close(() => {
        console.log('[server] Closed.');
        process.exit(0);
    });
});

process.on('SIGINT', () => {
    console.log('\n[server] SIGINT received, shutting down...');
    server.close(() => process.exit(0));
});

module.exports = app; // for testing
