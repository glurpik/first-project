# XMR Miner — Android + Web Dashboard

A complete Monero (XMR) CPU mining solution consisting of:

1. **Android App** (Kotlin) — mines via Stratum protocol, foreground service, real-time stats
2. **Web Dashboard** (HTML/CSS/JS + Chart.js) — live hashrate graphs, share tracking
3. **Stats API Server** (Node.js / Express) — bridges Android app ↔ web dashboard

---

## Project Structure

```
first-project/
├── android/                          # Android Studio project
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── java/com/cryptominer/app/
│   │       │   ├── MainActivity.kt     # UI, service binding, stats display
│   │       │   ├── MiningService.kt    # Foreground service orchestrator
│   │       │   ├── StratumClient.kt    # Stratum protocol (subscribe/authorize/submit)
│   │       │   ├── MiningWorker.kt     # CPU hashing loop (double-SHA256 demo)
│   │       │   └── StatsManager.kt     # Thread-safe stats + JSON file persistence
│   │       └── res/
│   │           ├── layout/activity_main.xml
│   │           ├── values/strings.xml
│   │           ├── values/colors.xml
│   │           ├── values/themes.xml
│   │           └── drawable/           # Shape drawables for UI elements
│   ├── build.gradle
│   ├── settings.gradle
│   └── gradle.properties
│
├── dashboard/                         # Web dashboard (static files)
│   ├── index.html
│   ├── css/dashboard.css
│   └── js/
│       ├── charts.js                  # Chart.js wrappers (hashrate + shares charts)
│       └── dashboard.js               # Data fetching, UI updates, demo mode
│
├── server/                            # Node.js stats API
│   ├── server.js
│   └── package.json
│
└── README.md
```

---

## Android App Setup

### Prerequisites
- Android Studio Hedgehog (2023.1) or later
- Android SDK 34
- JDK 17
- Kotlin 1.9.x

### Build & Run

1. Open the `android/` directory in Android Studio as a project.
2. Let Gradle sync complete.
3. Connect your Android device (API 24+ / Android 7.0+) or start an emulator.
4. Press **Run ▶**.

### Configuration
On first launch:

| Field | Description | Default |
|-------|-------------|---------|
| Wallet Address | Your 95-character XMR wallet address | (required) |
| Worker Name | Label for this mining device | `worker1` |
| Pool Host | Stratum pool hostname | `pool.supportxmr.com` |
| Pool Port | Stratum pool port | `3333` |

### What the App Does
- Connects to the pool via TCP Stratum protocol
- Sends `mining.subscribe` → `mining.authorize` → waits for `mining.notify`
- Runs a CPU hashing loop in a background coroutine
- Updates a persistent foreground notification with live hashrate
- Saves stats to `<external-files-dir>/mining_stats.json` every 2 seconds
- Broadcasts stats to the UI via `LocalBroadcastManager`

### Important Note on Hashing
The `MiningWorker` uses **double-SHA256** (not RandomX) for demonstration purposes.
Real Monero mining requires the **RandomX** algorithm, which must be compiled as
a native `.so` library and called via JNI. The Stratum connection, job management,
and stat reporting are fully functional; the hash function is the demo substitute.

To integrate real RandomX:
1. Build `RandomX` for `arm64-v8a` / `armeabi-v7a` using the Android NDK
2. Place `.so` files in `app/src/main/jniLibs/`
3. Write a JNI wrapper and call `randomx_calculate_hash()` from `MiningWorker.kt`

---

## Web Dashboard Setup

### Option A — With the Stats Server (recommended)

```bash
cd server
npm install
npm start          # runs on http://localhost:3000
```

Open `http://localhost:3000` in your browser. The server also serves the dashboard.

### Option B — Open directly in browser

Open `dashboard/index.html` directly. Click the **Demo Mode** toggle to see
simulated live data. (API calls will fail without the server, but demo mode works offline.)

### Dashboard Features
- **Hashrate Chart** — rolling 60-point line chart, updates every 5 seconds
- **Shares Chart** — bar chart showing accepted/rejected deltas per interval
- **KPI Cards** — hashrate, accepted shares, rejected shares, efficiency %
- **Worker Info** — pool, worker name, wallet address, data source
- **Demo Mode** — realistic simulated mining data for testing/demo
- **Auto-refresh** — 5-second interval with countdown indicator
- **Responsive** — works on mobile, tablet, and desktop

---

## Stats API Server

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the dashboard |
| `GET` | `/api/stats` | Returns current stats JSON |
| `POST` | `/api/stats` | Receives stats from Android app |
| `GET` | `/api/health` | Server health check |

### POST /api/stats — Request Body

```json
{
  "hashrate":        350.25,
  "accepted":        12,
  "rejected":        0,
  "total_hashes":    1250000,
  "uptime_seconds":  3600,
  "difficulty":      1024.0,
  "worker":          "worker1",
  "wallet":          "4...",
  "pool":            "pool.supportxmr.com:3333"
}
```

### Sending Stats from Android

In `StatsManager.saveToFile()`, add an HTTP POST alongside the file write:

```kotlin
// Add OkHttp dependency, then:
val json = buildStatsJson(hashrate)
val body = json.toString().toRequestBody("application/json".toMediaType())
val request = Request.Builder()
    .url("http://YOUR_SERVER_IP:3000/api/stats")
    .post(body)
    .build()
okHttpClient.newCall(request).enqueue(...)  // fire-and-forget
```

### Running with Custom Port

```bash
PORT=8080 npm start
```

---

## Supported Mining Pools (Stratum)

| Pool | Host | Port |
|------|------|------|
| SupportXMR | `pool.supportxmr.com` | `3333` |
| MoneroOcean | `gulf.moneroocean.stream` | `10128` |
| Nanopool | `xmr-eu1.nanopool.org` | `14444` |
| MineXMR | `pool.minexmr.com` | `4444` |

---

## Permissions (Android)

| Permission | Purpose |
|-----------|---------|
| `INTERNET` | Stratum pool connection |
| `FOREGROUND_SERVICE` | Background mining service |
| `WAKE_LOCK` | Keep CPU active during mining |
| `POST_NOTIFICATIONS` | Mining status notification (Android 13+) |
| `WRITE_EXTERNAL_STORAGE` | Save stats JSON (Android ≤ 9) |

---

## License

MIT — use freely for educational/personal purposes.  
Mining cryptocurrency may be regulated in your jurisdiction — check local laws.
