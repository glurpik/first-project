/**
 * charts.js — Chart.js setup and management for XMR Mining Dashboard
 *
 * Exports two chart instances:
 *   window.hashrateChart  — line chart showing hashrate over 60 minutes
 *   window.sharesChart    — bar chart showing accepted/rejected shares
 */

'use strict';

(function () {

    /* ---- Shared Chart Defaults ---- */
    Chart.defaults.color = '#9E9E9E';
    Chart.defaults.font.family = "'Courier New', monospace";
    Chart.defaults.font.size = 11;

    /* ---- Color palette ---- */
    const ORANGE       = '#FF6D00';
    const ORANGE_DIM   = 'rgba(255, 109, 0, 0.15)';
    const ORANGE_FADE  = 'rgba(255, 109, 0, 0)';
    const GREEN        = '#4CAF50';
    const GREEN_DIM    = 'rgba(76, 175, 80, 0.25)';
    const RED          = '#F44336';
    const RED_DIM      = 'rgba(244, 67, 54, 0.25)';
    const GRID_COLOR   = 'rgba(255, 255, 255, 0.05)';

    /* ---- Shared axis/grid config ---- */
    const sharedScales = {
        x: {
            grid: { color: GRID_COLOR, drawBorder: false },
            ticks: { maxTicksLimit: 8, maxRotation: 0 },
        },
        y: {
            grid: { color: GRID_COLOR, drawBorder: false },
            ticks: { maxTicksLimit: 6 },
            beginAtZero: true,
        },
    };

    /* ================================================================
       1. Hashrate Chart  (line, area fill, 60-point rolling window)
    ================================================================ */
    const hashrateCtx = document.getElementById('hashrateChart');

    // Create gradient fill
    function makeHashrateGradient(ctx, chartArea) {
        const grad = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
        grad.addColorStop(0, ORANGE_DIM);
        grad.addColorStop(1, ORANGE_FADE);
        return grad;
    }

    window.hashrateChart = new Chart(hashrateCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Hashrate',
                data: [],
                borderColor: ORANGE,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: ORANGE,
                tension: 0.4,
                fill: true,
                backgroundColor: function (context) {
                    const chart = context.chart;
                    const { ctx: c, chartArea } = chart;
                    if (!chartArea) return ORANGE_DIM;
                    return makeHashrateGradient(c, chartArea);
                },
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1A1A1A',
                    borderColor: ORANGE,
                    borderWidth: 1,
                    titleColor: '#9E9E9E',
                    bodyColor: ORANGE,
                    padding: 10,
                    callbacks: {
                        label: function (ctx) {
                            return ' ' + formatHashrate(ctx.parsed.y);
                        },
                    },
                },
            },
            scales: sharedScales,
        },
    });

    /* ================================================================
       2. Shares Chart  (bar, grouped accepted + rejected)
    ================================================================ */
    const sharesCtx = document.getElementById('sharesChart');

    window.sharesChart = new Chart(sharesCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Accepted',
                    data: [],
                    backgroundColor: GREEN_DIM,
                    borderColor: GREEN,
                    borderWidth: 1.5,
                    borderRadius: 4,
                    barPercentage: 0.6,
                },
                {
                    label: 'Rejected',
                    data: [],
                    backgroundColor: RED_DIM,
                    borderColor: RED,
                    borderWidth: 1.5,
                    borderRadius: 4,
                    barPercentage: 0.6,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 250 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: false, // handled in HTML
                },
                tooltip: {
                    backgroundColor: '#1A1A1A',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleColor: '#9E9E9E',
                    padding: 10,
                },
            },
            scales: {
                ...sharedScales,
                y: {
                    ...sharedScales.y,
                    ticks: {
                        stepSize: 1,
                        maxTicksLimit: 5,
                        callback: v => Number.isInteger(v) ? v : null,
                    },
                },
            },
        },
    });

    /* ================================================================
       Chart update helpers — called by dashboard.js
    ================================================================ */

    /**
     * Push a new hashrate data point.
     * @param {string} label - Time label (e.g. "14:03")
     * @param {number} value - Hashrate in H/s
     */
    window.pushHashratePoint = function (label, value) {
        const chart = window.hashrateChart;
        const MAX = 60;

        chart.data.labels.push(label);
        chart.data.datasets[0].data.push(value);

        if (chart.data.labels.length > MAX) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
        }

        chart.update('none');
    };

    /**
     * Push new shares data point.
     * @param {string} label
     * @param {number} accepted
     * @param {number} rejected
     */
    window.pushSharesPoint = function (label, accepted, rejected) {
        const chart = window.sharesChart;
        const MAX = 30;

        chart.data.labels.push(label);
        chart.data.datasets[0].data.push(accepted);
        chart.data.datasets[1].data.push(rejected);

        if (chart.data.labels.length > MAX) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
            chart.data.datasets[1].data.shift();
        }

        chart.update('none');
    };

    /**
     * Clear all chart data (e.g. on miner reconnect).
     */
    window.clearCharts = function () {
        [window.hashrateChart, window.sharesChart].forEach(c => {
            c.data.labels = [];
            c.data.datasets.forEach(d => (d.data = []));
            c.update('none');
        });
    };

    /* ---- Utility ---- */
    function formatHashrate(hps) {
        if (hps >= 1e6) return (hps / 1e6).toFixed(2) + ' MH/s';
        if (hps >= 1e3) return (hps / 1e3).toFixed(2) + ' KH/s';
        return hps.toFixed(2) + ' H/s';
    }

})();
