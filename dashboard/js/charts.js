const CHART_COLORS = {
    primary: '#ff6d00',
    primaryAlpha: 'rgba(255, 109, 0, 0.15)',
    green: '#4caf50',
    greenAlpha: 'rgba(76, 175, 80, 0.15)',
    red: '#ef5350',
    redAlpha: 'rgba(239, 83, 80, 0.15)',
    blue: '#42a5f5',
    grid: '#1e1e1e',
    text: '#666',
};

const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: '#1a1a1a',
            borderColor: '#333',
            borderWidth: 1,
            titleColor: '#fff',
            bodyColor: '#aaa',
        }
    },
    scales: {
        x: {
            grid: { color: CHART_COLORS.grid },
            ticks: { color: CHART_COLORS.text, maxTicksLimit: 8 }
        },
        y: {
            grid: { color: CHART_COLORS.grid },
            ticks: { color: CHART_COLORS.text }
        }
    }
};

function initHashrateChart() {
    const ctx = document.getElementById('hashrateChart').getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Hashrate',
                data: [],
                borderColor: CHART_COLORS.primary,
                backgroundColor: CHART_COLORS.primaryAlpha,
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 4,
            }]
        },
        options: {
            ...chartDefaults,
            scales: {
                ...chartDefaults.scales,
                y: {
                    ...chartDefaults.scales.y,
                    beginAtZero: true,
                    ticks: {
                        color: CHART_COLORS.text,
                        callback: (v) => v >= 1000 ? `${(v/1000).toFixed(1)}K` : v.toFixed(1)
                    }
                }
            }
        }
    });
}

function initSharesChart() {
    const ctx = document.getElementById('sharesChart').getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Accepted',
                    data: [],
                    backgroundColor: CHART_COLORS.greenAlpha,
                    borderColor: CHART_COLORS.green,
                    borderWidth: 1,
                },
                {
                    label: 'Rejected',
                    data: [],
                    backgroundColor: CHART_COLORS.redAlpha,
                    borderColor: CHART_COLORS.red,
                    borderWidth: 1,
                }
            ]
        },
        options: {
            ...chartDefaults,
            plugins: {
                ...chartDefaults.plugins,
                legend: {
                    display: true,
                    labels: { color: '#aaa', boxWidth: 12, font: { size: 11 } }
                }
            },
            scales: {
                ...chartDefaults.scales,
                y: { ...chartDefaults.scales.y, beginAtZero: true }
            }
        }
    });
}

function initEfficiencyChart() {
    const ctx = document.getElementById('efficiencyChart').getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Efficiency %',
                data: [],
                borderColor: CHART_COLORS.blue,
                backgroundColor: 'rgba(66,165,245,0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
            }]
        },
        options: {
            ...chartDefaults,
            scales: {
                ...chartDefaults.scales,
                y: {
                    ...chartDefaults.scales.y,
                    min: 0,
                    max: 100,
                    ticks: { color: CHART_COLORS.text, callback: (v) => `${v}%` }
                }
            }
        }
    });
}
