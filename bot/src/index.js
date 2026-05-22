'use strict';

const { Worker } = require('worker_threads');
const fs = require('fs');
const path = require('path');
const { writeRow } = require('./csvWriter');

// ── Config ────────────────────────────────────────────────────────────────────
const CONFIG = {
  host: process.env.MC_HOST || 'mc.yugame.ru',
  port: parseInt(process.env.MC_PORT || '25565', 10),
  version: process.env.MC_VERSION || '1.20.1',
  auth: 'offline',          // Change to 'microsoft' for licensed accounts
};

const THREADS = parseInt(process.env.THREADS || '5', 10);
const MAX_RETRIES = parseInt(process.env.MAX_RETRIES || '3', 10);
const ACCOUNTS_FILE = process.env.ACCOUNTS_FILE || path.join(__dirname, '..', 'accounts.txt');
const OUTPUT_DIR = path.join(__dirname, '..', 'output');

// ── Ensure output directory exists ────────────────────────────────────────────
if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// ── Load accounts ─────────────────────────────────────────────────────────────
function loadAccounts(filePath) {
  if (!fs.existsSync(filePath)) {
    console.error(`[ERROR] accounts.txt not found at: ${filePath}`);
    process.exit(1);
  }
  return fs
    .readFileSync(filePath, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [login, ...rest] = l.split(':');
      return { login: login.trim(), password: rest.join(':').trim() };
    })
    .filter((a) => a.login && a.password);
}

// ── Worker pool ───────────────────────────────────────────────────────────────
async function processAccount(account) {
  return new Promise((resolve) => {
    const worker = new Worker(path.join(__dirname, 'worker.js'), {
      workerData: { config: CONFIG, account, maxRetries: MAX_RETRIES },
    });

    worker.on('message', async (msg) => {
      if (msg.success) {
        const r = msg.result;
        console.log(`[${r.status.toUpperCase()}] ${r.login} → coins:${r.coins} tokens:${r.tokens} rep:${r.reputation} donate:${r.donate}`);
        await writeRow(r).catch(() => {});
        resolve(r);
      } else {
        console.error(`[FAIL] ${account.login}: ${msg.error}`);
        await writeRow({
          login: account.login,
          oldPassword: account.password,
          newPassword: '',
          status: 'error',
          coins: '', tokens: '', cashback: '', reputation: '', donate: '',
          error: msg.error,
        }).catch(() => {});
        resolve(null);
      }
    });

    worker.on('error', async (err) => {
      console.error(`[WORKER ERROR] ${account.login}: ${err.message}`);
      resolve(null);
    });

    worker.on('exit', (code) => {
      if (code !== 0) resolve(null);
    });
  });
}

async function runPool(accounts) {
  let index = 0;
  let running = 0;
  let done = 0;
  const total = accounts.length;

  return new Promise((resolve) => {
    function next() {
      while (running < THREADS && index < total) {
        const account = accounts[index++];
        running++;
        processAccount(account).then(() => {
          running--;
          done++;
          process.stdout.write(`\r[PROGRESS] ${done}/${total} done, ${running} running  `);
          if (done === total) resolve();
          else next();
        });
      }
    }
    next();
  });
}

// ── Entry point ───────────────────────────────────────────────────────────────
(async () => {
  const accounts = loadAccounts(ACCOUNTS_FILE);
  console.log(`[START] Loaded ${accounts.length} accounts | threads: ${THREADS} | server: ${CONFIG.host}:${CONFIG.port}`);
  await runPool(accounts);
  console.log('\n[DONE] All accounts processed.');
  process.exit(0);
})();
