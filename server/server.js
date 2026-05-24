const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// In-memory stats store
let latestStats = {
    hashrate: 0,
    accepted: 0,
    rejected: 0,
    total_hashes: 0,
    uptime_seconds: 0,
    difficulty: 0,
    efficiency: 0,
    timestamp: null,
    worker: 'unknown',
    online: false
};

// Serve dashboard
app.use('/', express.static(path.join(__dirname, '../dashboard')));

// Receive stats from Android app
app.post('/api/stats', (req, res) => {
    const data = req.body;
    if (!data) return res.status(400).json({ error: 'No data' });

    const total = (data.accepted || 0) + (data.rejected || 0);
    latestStats = {
        hashrate: data.hashrate || 0,
        accepted: data.accepted || 0,
        rejected: data.rejected || 0,
        total_hashes: data.total_hashes || 0,
        uptime_seconds: data.uptime_seconds || 0,
        difficulty: data.difficulty || 0,
        efficiency: total > 0 ? ((data.accepted / total) * 100).toFixed(1) : 100,
        timestamp: Date.now(),
        worker: data.worker || 'unknown',
        online: true
    };

    console.log(`[${new Date().toISOString()}] Stats: ${latestStats.hashrate.toFixed(2)} H/s | ${latestStats.accepted}/${total} shares`);
    res.json({ ok: true });
});

// Serve stats to dashboard
app.get('/api/stats', (req, res) => {
    // Mark offline if no update in 30s
    if (latestStats.timestamp && Date.now() - latestStats.timestamp > 30_000) {
        latestStats.online = false;
    }
    res.json(latestStats);
});

// Health check
app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', uptime: process.uptime() });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`XMR Miner Stats Server running on http://0.0.0.0:${PORT}`);
    console.log(`Dashboard: http://localhost:${PORT}`);
    console.log(`Stats API: http://localhost:${PORT}/api/stats`);
});
