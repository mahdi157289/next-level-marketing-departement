#!/usr/bin/env node
/**
 * CLI wrapper for superleadfinder/scraper.js
 * Usage: node run-scrape.js <query> <region> <maxResults> <headless>
 * Outputs JSON array of leads to stdout when complete.
 */
const path = require('path');
const scraperPath = path.resolve(__dirname);
const { runScraper } = require(path.join(scraperPath, 'scraper.js'));

const query = process.argv[2] || '';
const region = process.argv[3] || '';
const maxResults = parseInt(process.argv[4] || '10', 10);
const headless = process.argv[5] !== 'false';

const fullQuery = `${query} ${region}`.trim();
const leads = [];

function onLog(msg) {
    // Send logs to stderr so they don't interfere with JSON stdout
    console.error(`[LOG] ${msg}`);
}

function onProgress(current) {
    // Send progress to stderr
    console.error(`[PROGRESS] ${current}`);
}

function onLeadScaped(lead) {
    leads.push(lead);
    // Send each lead as JSON to stdout for streaming (optional)
    process.stdout.write(JSON.stringify({ type: 'lead', data: lead }) + '\n');
}

const cancelToken = { isCancelled: false };

// Listen for SIGINT/SIGTERM for graceful cancellation
process.on('SIGINT', () => { cancelToken.isCancelled = true; });
process.on('SIGTERM', () => { cancelToken.isCancelled = true; });

(async () => {
    try {
        await runScraper(fullQuery, maxResults, headless, onLog, onProgress, onLeadScaped, cancelToken);
        // Output final summary as JSON to stdout
        console.log(JSON.stringify({ type: 'complete', count: leads.length, leads: leads }));
        process.exit(0);
    } catch (err) {
        console.error(`[ERROR] ${err.message}`);
        console.log(JSON.stringify({ type: 'error', message: err.message }));
        process.exit(1);
    }
})();
