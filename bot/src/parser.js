'use strict';

/**
 * Strip Minecraft color/format codes (§x) and return plain text.
 */
function stripColors(text) {
  return text.replace(/§[0-9a-fk-or]/gi, '').trim();
}

/**
 * Parse scoreboard lines into a key→value map.
 * Mineflayer exposes bot.scoreboard; we read the sidebar objective.
 */
function parseScoreboard(bot) {
  const result = { coins: null, tokens: null };
  try {
    const sidebar = bot.scoreboard.sidebar;
    if (!sidebar) return result;

    for (const item of Object.values(sidebar.itemsMap || {})) {
      const name = stripColors(item.name || '').toLowerCase();
      const score = item.value ?? item.score;

      if (/монет|coins?/i.test(name)) result.coins = score;
      else if (/токен|token/i.test(name)) result.tokens = score;
    }
  } catch (_) { /* scoreboard not ready */ }
  return result;
}

/**
 * Wait for a chat message matching `predicate` within `timeout` ms.
 * Returns the matched message string, or null on timeout.
 */
function waitForChat(bot, predicate, timeout = 8000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      bot.removeListener('message', handler);
      resolve(null);
    }, timeout);

    function handler(jsonMsg) {
      const text = stripColors(jsonMsg.toString());
      if (predicate(text)) {
        clearTimeout(timer);
        bot.removeListener('message', handler);
        resolve(text);
      }
    }

    bot.on('message', handler);
  });
}

/**
 * Parse /cashback response — looks for a number after "кэшбэк" / "cashback".
 */
function parseCashback(text) {
  const m = text.match(/кэшбэк[:\s]*([0-9,.]+)/i)
    || text.match(/cashback[:\s]*([0-9,.]+)/i)
    || text.match(/([0-9,.]+)\s*(?:монет|coins?)/i);
  return m ? m[1].replace(',', '.') : null;
}

/**
 * Parse /report list response for reputation value.
 */
function parseReputation(text) {
  const m = text.match(/репутац[^\d]*([+-]?\d+)/i)
    || text.match(/reputation[:\s]*([+-]?\d+)/i)
    || text.match(/([+-]?\d+)\s*репутац/i);
  return m ? m[1] : null;
}

/**
 * Parse /profile response — donation rank / status.
 */
function parseDonate(text) {
  const m = text.match(/донат[:\s]*([^\n,]+)/i)
    || text.match(/(?:ранг|rank)[:\s]*([^\n,]+)/i)
    || text.match(/(?:premium|VIP|MVP|LEGEND|ULTRA|ETERNAL|SUPREME|IMMORTAL)/i);
  return m ? m[1]?.trim() ?? m[0]?.trim() : 'none';
}

module.exports = { stripColors, parseScoreboard, waitForChat, parseCashback, parseReputation, parseDonate };
