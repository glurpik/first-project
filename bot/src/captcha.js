'use strict';

const axios = require('axios');
const FormData = require('form-data');

// Captcha model config — point to your local model server or API
const CAPTCHA_API_URL = process.env.CAPTCHA_API_URL || 'http://localhost:5000/predict';
const CAPTCHA_API_KEY = process.env.CAPTCHA_API_KEY || '';

/**
 * Solve captcha by sending image bytes to your model endpoint.
 * Expected response: { result: "ABCD" }
 *
 * Replace the body of this function if your model has a different interface.
 */
async function solveCaptcha(imageBuffer) {
  try {
    const form = new FormData();
    form.append('image', imageBuffer, { filename: 'captcha.png', contentType: 'image/png' });

    const headers = { ...form.getHeaders() };
    if (CAPTCHA_API_KEY) headers['Authorization'] = `Bearer ${CAPTCHA_API_KEY}`;

    const response = await axios.post(CAPTCHA_API_URL, form, { headers, timeout: 15000 });

    const text = response.data?.result || response.data?.text || response.data;
    if (!text || typeof text !== 'string') throw new Error('Empty captcha response');
    return text.trim().toUpperCase();
  } catch (err) {
    throw new Error(`Captcha solve failed: ${err.message}`);
  }
}

/**
 * Fallback: solve captcha from a text string (some servers send captcha as chat text).
 * If captcha is just digits — you may not need an image model at all.
 */
function extractCaptchaFromText(text) {
  // YuGame typically sends: "Введите капчу: XXXX"
  const match = text.match(/капч[уа][:\s]+([A-Za-z0-9]{4,8})/i)
    || text.match(/[Cc]aptcha[:\s]+([A-Za-z0-9]{4,8})/)
    || text.match(/\b([A-Z0-9]{4,8})\b/);
  return match ? match[1].trim() : null;
}

module.exports = { solveCaptcha, extractCaptchaFromText };
