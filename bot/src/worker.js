'use strict';

const { workerData, parentPort } = require('worker_threads');
const { runBot } = require('./bot');

const { config, account, maxRetries } = workerData;

async function run() {
  let lastError;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const result = await runBot(config, account);
      parentPort.postMessage({ success: true, result });
      return;
    } catch (err) {
      lastError = err;
      const delay = Math.min(2000 * 2 ** (attempt - 1), 30000);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  parentPort.postMessage({ success: false, error: lastError?.message ?? 'Unknown error', account });
}

run();
