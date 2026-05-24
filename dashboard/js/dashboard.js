// API endpoint — set to your server URL, or null to use demo data
const API_URL = null; // e.g. 'http://192.168.1.100:3000/api/stats'

const REFRESH_INTERVAL = 5000;
const MAX_HISTORY = 60;

let hashrateChart, sharesChart, efficiencyChart;
let historyLabels = [];
let hashrateHistory = [];
let acceptedHistory = [];
let rejectedHistory = [];
let efficiencyHistory = [];
let prevAccepted = 0, prevRejected = 0;
let countdown = REFRESH_INTERVAL / 1000;
let isOnline = false;

// Demo data simulation
let demoHashrate = 150;
let demoAccepted = 0;
let demoRejected = 0;
let demoUptime = 0;
let demoTick = 0;

function generateDemoStats() {
    demoTick++;
    demoUptime += REFRESH_INTERVAL / 1000;

    // Simulate variable hashrate (100-200 H/s)
    demoHashrate += (Math.random() - 0.5) * 30;
    demoHashrate = Math.max(80, Math.min(250, demoHashrate));

    // Occasionally accept a share
    if (demoTick % 6 === 0) demoAccepted++;
    if (demoTick % 40 === 0) demoRejected++;

    const total = demoAccepted + demoRejected;
    return {
        hashrate: demoHashrate,
        accepted: demoAccepted,
        rejected: demoRejected,
        total_hashes: Math.floor(demoHashrate * demoUptime),
        uptime_seconds: Math.floor(demoUptime),
        difficulty: 65536,
        efficiency: total > 0 ? (demoAccepted / total * 100).toFixed(1) : 100,
        timestamp: Date.now(),
        demo: true
    };
}

async function fetchStats() {
    if (!API_URL) return generateDemoStats();
    try {
        const res = await fetch(API_URL, { signal: AbortSignal.timeout(4000) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        return null;
    }
}

function formatHashrate(hps) {
    if (hps >= 1_000_000) return { value: (hps / 1_000_000).toFixed(2), unit: 'MH/s' };
    if (hps >= 1_000)     return { value: (hps / 1_000).toFixed(2), unit: 'KH/s' };
    return { value: hps.toFixed(2), unit: 'H/s' };
}

function formatNumber(n) {
    if (n >= 1e9) return `${(n / 1e9).toFixed(2)}G`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return n.toString();
}

function formatUptime(secs) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function formatTime(ts) {
    return new Date(ts).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function setOnline(online) {
    if (isOnline === online) return;
    isOnline = online;
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    dot.className = `status-dot ${online ? 'online' : 'offline'}`;
    txt.textContent = online ? 'Online' : 'Offline';
}

function updateUI(stats) {
    if (!stats) {
        setOnline(false);
        return;
    }

    setOnline(true);

    // Hashrate
    const hr = formatHashrate(stats.hashrate || 0);
    document.getElementById('hashrate').textContent = hr.value;
    document.getElementById('hashrateUnit').textContent = hr.unit;

    // Shares
    document.getElementById('accepted').textContent = stats.accepted || 0;
    document.getElementById('rejected').textContent = stats.rejected || 0;

    // Efficiency
    const eff = parseFloat(stats.efficiency || 0);
    document.getElementById('efficiency').textContent = eff.toFixed(1);

    // Secondary
    document.getElementById('totalHashes').textContent = formatNumber(stats.total_hashes || 0);
    document.getElementById('uptime').textContent = formatUptime(stats.uptime_seconds || 0);
    document.getElementById('difficulty').textContent = stats.difficulty ? formatNumber(stats.difficulty) : '—';
    document.getElementById('lastUpdate').textContent = stats.timestamp ? formatTime(stats.timestamp) : '—';

    // Demo badge
    const demoBadge = document.getElementById('demoMode');
    demoBadge.className = stats.demo ? 'demo-badge' : 'demo-badge hidden';

    // Update chart history
    const label = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

    historyLabels.push(label);
    hashrateHistory.push(stats.hashrate || 0);

    const newAccepted = (stats.accepted || 0) - prevAccepted;
    const newRejected = (stats.rejected || 0) - prevRejected;
    acceptedHistory.push(Math.max(0, newAccepted));
    rejectedHistory.push(Math.max(0, newRejected));
    efficiencyHistory.push(eff);

    prevAccepted = stats.accepted || 0;
    prevRejected = stats.rejected || 0;

    // Keep max history
    if (historyLabels.length > MAX_HISTORY) {
        historyLabels.shift();
        hashrateHistory.shift();
        acceptedHistory.shift();
        rejectedHistory.shift();
        efficiencyHistory.shift();
    }

    // Update charts
    hashrateChart.data.labels = [...historyLabels];
    hashrateChart.data.datasets[0].data = [...hashrateHistory];
    hashrateChart.update('none');

    sharesChart.data.labels = [...historyLabels];
    sharesChart.data.datasets[0].data = [...acceptedHistory];
    sharesChart.data.datasets[1].data = [...rejectedHistory];
    sharesChart.update('none');

    efficiencyChart.data.labels = [...historyLabels];
    efficiencyChart.data.datasets[0].data = [...efficiencyHistory];
    efficiencyChart.update('none');
}

function startCountdown() {
    countdown = REFRESH_INTERVAL / 1000;
    const el = document.getElementById('countdown');
    el.textContent = countdown;

    const timer = setInterval(() => {
        countdown--;
        el.textContent = Math.max(0, countdown);
        if (countdown <= 0) clearInterval(timer);
    }, 1000);
}

async function refresh() {
    const stats = await fetchStats();
    updateUI(stats);
    startCountdown();
}

function init() {
    hashrateChart = initHashrateChart();
    sharesChart = initSharesChart();
    efficiencyChart = initEfficiencyChart();

    refresh();
    setInterval(refresh, REFRESH_INTERVAL);
}

document.addEventListener('DOMContentLoaded', init);
