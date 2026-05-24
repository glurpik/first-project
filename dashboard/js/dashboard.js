/**
 * dashboard.js — Main dashboard logic for XMR Mining Dashboard
 *
 * Features:
 *  - Auto-refresh every 5 seconds
 *  - Fetches stats from REST API (GET /api/stats)
 *  - Falls back to mock/demo data when API is unavailable or demo mode is on
 *  - Updates all KPI cards, chart data, and status indicators
 */

'use strict';

(function () {

    /* ================================================================
       Configuration
    ================================================================ */
    const API_URL         = '/api/stats';     // Express server endpoint
    const REFRESH_INTERVAL = 5000;            // ms

    /* ================================================================
       State
    ================================================================ */
    let demoMode         = false;
    let refreshTimer     = null;
    let countdownTimer   = null;
    let countdownValue   = REFRESH_INTERVAL / 1000;
    let isOnline         = false;

    // Demo state — tracks a simulated miner
    const demo = {
        hashrate:      0,
        accepted:      0,
        rejected:      0,
        totalHashes:   0,
        uptime:        0,
        difficulty:    1024,
        startTime:     Date.now(),
        // simulated hashrate trends
        baseHashrate:  350,
        variance:      80,
    };

    // Previous accepted/rejected for per-interval delta (shares chart)
    let prevAccepted = 0;
    let prevRejected = 0;

    /* ================================================================
       DOM references
    ================================================================ */
    const $ = id => document.getElementById(id);

    const els = {
        workerStatus:    $('workerStatus'),
        statusDot:       $('statusDot'),
        statusText:      $('statusText'),
        refreshBadge:    $('refreshBadge'),
        refreshCountdown: $('refreshCountdown'),
        kpiHashrate:     $('kpiHashrate'),
        kpiHashrateSub:  $('kpiHashrateSub'),
        kpiAccepted:     $('kpiAccepted'),
        kpiAcceptedSub:  $('kpiAcceptedSub'),
        kpiRejected:     $('kpiRejected'),
        kpiRejectedSub:  $('kpiRejectedSub'),
        kpiEfficiency:   $('kpiEfficiency'),
        kpiEfficiencySub: $('kpiEfficiencySub'),
        sideUptime:      $('sideUptime'),
        sideTotalHashes: $('sideTotalHashes'),
        sideDifficulty:  $('sideDifficulty'),
        sideLastUpdate:  $('sideLastUpdate'),
        workerPool:      $('workerPool'),
        workerName:      $('workerName'),
        workerWallet:    $('workerWallet'),
        dataSource:      $('dataSource'),
        demoToggle:      $('demoModeToggle'),
    };

    /* ================================================================
       Demo Mode Toggle
    ================================================================ */
    els.demoToggle.addEventListener('change', function () {
        demoMode = this.checked;
        if (demoMode) {
            // Reset demo state
            Object.assign(demo, {
                hashrate: 0, accepted: 0, rejected: 0,
                totalHashes: 0, uptime: 0,
                startTime: Date.now(),
            });
            prevAccepted = 0;
            prevRejected = 0;
            clearCharts();
            els.dataSource.textContent = 'Demo (simulated)';
        } else {
            els.dataSource.textContent = 'REST API';
        }
        refresh();
    });

    /* ================================================================
       Main refresh loop
    ================================================================ */
    function startRefreshLoop() {
        refresh();
        refreshTimer = setInterval(refresh, REFRESH_INTERVAL);
        startCountdown();
    }

    function startCountdown() {
        countdownValue = REFRESH_INTERVAL / 1000;
        updateCountdown();
        countdownTimer = setInterval(() => {
            countdownValue--;
            if (countdownValue <= 0) countdownValue = REFRESH_INTERVAL / 1000;
            updateCountdown();
        }, 1000);
    }

    function updateCountdown() {
        els.refreshCountdown.textContent = countdownValue + 's';
    }

    async function refresh() {
        // Flash refresh badge
        els.refreshBadge.classList.add('refreshing');
        setTimeout(() => els.refreshBadge.classList.remove('refreshing'), 500);

        if (demoMode) {
            updateWithDemoData();
        } else {
            await fetchAndUpdate();
        }
    }

    /* ================================================================
       API fetch
    ================================================================ */
    async function fetchAndUpdate() {
        try {
            const response = await fetch(API_URL, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                signal: AbortSignal.timeout(4000),
            });

            if (!response.ok) throw new Error('HTTP ' + response.status);

            const data = await response.json();
            setOnlineStatus(true);
            updateUI(data);
            els.dataSource.textContent = 'REST API ✓';

        } catch (err) {
            console.warn('[Dashboard] API fetch failed:', err.message);
            setOnlineStatus(false);
            els.dataSource.textContent = 'API offline — enable Demo Mode';
        }
    }

    /* ================================================================
       Demo data generator
    ================================================================ */
    function updateWithDemoData() {
        const elapsed = (Date.now() - demo.startTime) / 1000;
        demo.uptime = Math.floor(elapsed);

        // Simulate hashrate with realistic fluctuation
        const noise = (Math.random() - 0.5) * 2 * demo.variance;
        const trend = Math.sin(elapsed / 60) * 40; // gentle sine wave
        demo.hashrate = Math.max(50, demo.baseHashrate + trend + noise);

        // Increment total hashes
        demo.totalHashes += Math.floor(demo.hashrate * (REFRESH_INTERVAL / 1000));

        // Occasionally find a share (roughly every 15-30s)
        if (Math.random() < 0.25) {
            demo.accepted++;
            if (Math.random() < 0.04) { // ~4% rejection rate
                demo.rejected++;
            }
        }

        setOnlineStatus(true);
        updateUI({
            hashrate:      demo.hashrate,
            accepted:      demo.accepted,
            rejected:      demo.rejected,
            total_hashes:  demo.totalHashes,
            uptime_seconds: demo.uptime,
            difficulty:    demo.difficulty,
            timestamp:     Date.now(),
            worker:        'demo-worker1',
            wallet:        '4...demo...wallet',
            pool:          'pool.supportxmr.com:3333',
        });
    }

    /* ================================================================
       UI update
    ================================================================ */
    function updateUI(data) {
        const hashrate    = parseFloat(data.hashrate)      || 0;
        const accepted    = parseInt(data.accepted)        || 0;
        const rejected    = parseInt(data.rejected)        || 0;
        const totalHashes = parseInt(data.total_hashes)    || 0;
        const uptime      = parseInt(data.uptime_seconds)  || 0;
        const difficulty  = parseFloat(data.difficulty)    || 0;

        const total      = accepted + rejected;
        const efficiency = total > 0 ? ((accepted / total) * 100).toFixed(1) : '0.0';
        const rejectRate = total > 0 ? ((rejected / total) * 100).toFixed(1) : '0.0';

        // KPIs
        flashUpdate(els.kpiHashrate,   formatHashrate(hashrate));
        els.kpiHashrateSub.textContent = hashrate > 0 ? 'Active mining' : 'Idle';

        flashUpdate(els.kpiAccepted,   accepted.toString());
        els.kpiAcceptedSub.textContent = accepted > 0 ? 'Last: just now' : 'No shares yet';

        flashUpdate(els.kpiRejected,   rejected.toString());
        els.kpiRejectedSub.textContent = 'Error rate: ' + rejectRate + '%';

        flashUpdate(els.kpiEfficiency, efficiency + '%');
        els.kpiEfficiencySub.textContent = accepted + ' / ' + total + ' shares';

        // Side panel
        els.sideUptime.textContent      = formatUptime(uptime);
        els.sideTotalHashes.textContent = formatNumber(totalHashes);
        els.sideDifficulty.textContent  = difficulty > 0 ? formatNumber(difficulty) : '--';
        els.sideLastUpdate.textContent  = new Date().toLocaleTimeString();

        // Worker info
        if (data.pool)   els.workerPool.textContent   = data.pool;
        if (data.worker) els.workerName.textContent   = data.worker;
        if (data.wallet) els.workerWallet.textContent = truncateWallet(data.wallet);

        // Charts
        const timeLabel = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        pushHashratePoint(timeLabel, hashrate);

        const deltaAccepted = accepted - prevAccepted;
        const deltaRejected = rejected - prevRejected;
        pushSharesPoint(timeLabel, Math.max(0, deltaAccepted), Math.max(0, deltaRejected));
        prevAccepted = accepted;
        prevRejected = rejected;
    }

    /* ================================================================
       Status indicator
    ================================================================ */
    function setOnlineStatus(online) {
        isOnline = online;
        if (online) {
            els.workerStatus.classList.add('online');
            els.statusText.textContent = 'Online';
        } else {
            els.workerStatus.classList.remove('online');
            els.statusText.textContent = 'Offline';
        }
    }

    /* ================================================================
       Helpers
    ================================================================ */
    function formatHashrate(hps) {
        if (hps >= 1e6) return (hps / 1e6).toFixed(2) + ' MH/s';
        if (hps >= 1e3) return (hps / 1e3).toFixed(2) + ' KH/s';
        return hps.toFixed(2) + ' H/s';
    }

    function formatNumber(n) {
        if (n >= 1e9) return (n / 1e9).toFixed(2) + 'G';
        if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(2) + 'K';
        return n.toString();
    }

    function formatUptime(secs) {
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = secs % 60;
        return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
    }

    function truncateWallet(w) {
        if (!w || w.length < 10) return w;
        return w.slice(0, 8) + '...' + w.slice(-6);
    }

    // Flash an element when its value changes
    function flashUpdate(el, newValue) {
        if (el.textContent !== newValue) {
            el.textContent = newValue;
            el.classList.remove('flash');
            // Force reflow then re-add class
            void el.offsetWidth;
            el.classList.add('flash');
        }
    }

    /* ================================================================
       Boot
    ================================================================ */
    // Default to demo mode if API is likely not available (detected later)
    els.dataSource.textContent = 'REST API';
    startRefreshLoop();

})();
