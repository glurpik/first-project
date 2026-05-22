'use strict';

const { createObjectCsvWriter } = require('csv-writer');
const path = require('path');

const OUTPUT_DIR = path.join(__dirname, '..', 'output');
const CSV_PATH = path.join(OUTPUT_DIR, 'results.csv');

const writer = createObjectCsvWriter({
  path: CSV_PATH,
  header: [
    { id: 'login',       title: 'Login' },
    { id: 'oldPassword', title: 'OldPassword' },
    { id: 'newPassword', title: 'NewPassword' },
    { id: 'status',      title: 'Status' },
    { id: 'coins',       title: 'Coins' },
    { id: 'tokens',      title: 'Tokens' },
    { id: 'cashback',    title: 'Cashback' },
    { id: 'reputation',  title: 'Reputation' },
    { id: 'donate',      title: 'Donate' },
    { id: 'error',       title: 'Error' },
  ],
  append: true,
});

// Write CSV header once on first run
const fs = require('fs');
if (!fs.existsSync(CSV_PATH)) {
  fs.writeFileSync(CSV_PATH,
    'Login,OldPassword,NewPassword,Status,Coins,Tokens,Cashback,Reputation,Donate,Error\n',
    'utf8'
  );
}

async function writeRow(row) {
  await writer.writeRecords([row]);
}

module.exports = { writeRow, CSV_PATH };
