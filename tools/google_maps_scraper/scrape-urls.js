#!/usr/bin/env node
/**
 * Re-scrape individual Google Maps place URLs with one shared browser.
 * Usage: node scrape-urls.js <url1> <url2> ...
 *        echo "url1\nurl2" | node scrape-urls.js
 * Prints each place as a {type:'lead', data} JSON line on stdout.
 */
const readline = require('readline');
const { chromium } = require('playwright');
const { scrapeCurrentPlace } = require('./scraper.js');

const urls = process.argv.slice(2);
const rl = readline.createInterface({ input: process.stdin });

rl.on('line', (line) => {
  const u = (line || '').trim();
  if (u && !urls.includes(u)) {
    urls.push(u);
  }
});

rl.on('close', () => {
  if (!urls.length) {
    console.error('[ERROR] no urls provided');
    process.exit(1);
  }
  main(urls);
});

function onLog(msg) {
  console.error(`[LOG] ${msg}`);
}

async function main(urls) {
  const browser = await chromium.launch({
    headless: true,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox'],
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 800 },
    locale: 'en-US',
  });
  const page = await context.newPage();

  for (const targetUrl of urls) {
    try {
      onLog(`Opening ${targetUrl}`);
      await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await page.waitForTimeout(1200 + Math.random() * 600);
      const lead = await scrapeCurrentPlace(page, targetUrl, onLog);
      process.stdout.write(JSON.stringify({ type: 'lead', data: lead }) + '\n');
    } catch (err) {
      console.error(`[ERROR] ${targetUrl}: ${err.message}`);
      process.stdout.write(JSON.stringify({ type: 'error', url: targetUrl, message: err.message }) + '\n');
    }
  }

  await browser.close();
  process.exit(0);
}
