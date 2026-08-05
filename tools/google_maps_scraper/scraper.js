const { chromium } = require('playwright');

/**
 * Runs the Google Maps Scraper.
 * @param {string} query The search query (e.g. "construction companies in Surrey BC")
 * @param {number} maxResults The maximum number of results to fetch
 * @param {boolean} headless Run in headless mode
 * @param {function} onLog Callback for log messages
 * @param {function} onProgress Callback for progress updates
 * @param {function} onLeadScraped Callback when a lead is successfully scraped
 * @param {object} cancelToken Object to monitor cancellation
 */
async function runScraper(query, maxResults = 20, headless = true, onLog, onProgress, onLeadScraped, cancelToken) {
  onLog(`Launching browser (headless: ${headless})...`);
  
  // Set up standard Chrome arguments to evade basic bot detection
  const browser = await chromium.launch({
    headless: headless,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--no-sandbox',
      '--disable-setuid-sandbox'
    ]
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 800 },
    locale: 'en-US'
  });

  const page = await context.newPage();

  // Helper to check for cancel request
  const checkCancelled = () => cancelToken && cancelToken.isCancelled;

  try {
    const searchUrl = `https://www.google.com/maps/search/${encodeURIComponent(query)}`;
    onLog(`Navigating to search URL: ${searchUrl}`);
    await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

    if (checkCancelled()) {
      onLog("Scraping cancelled before search results loaded.");
      return;
    }

    // Check if Google Maps redirected us directly to a single business page
    if (page.url().includes('/maps/place/')) {
      onLog("Google Maps redirected directly to a single business page.");
      const lead = await scrapeCurrentPlace(page, page.url(), onLog);
      onLeadScraped(lead);
      onProgress(1, 1);
      return;
    }

    // Wait for the side results panel (div[role="feed"]) to load
    onLog("Waiting for results list to load...");
    try {
      await page.waitForSelector('div[role="feed"]', { timeout: 15000 });
    } catch (err) {
      onLog("Warning: Could not find feed panel. Google Maps UI might have changed or there are no results.");
      // fallback check
      const feedExists = await page.locator('div[role="feed"]').count();
      if (!feedExists) {
        const bodyText = await page.innerText('body');
        if (bodyText.includes("Google Maps can't find") || bodyText.includes("No results found")) {
          onLog("No results found on Google Maps for this query.");
          return;
        }
        throw new Error("Search results page failed to load correctly.");
      }
    }

    const feedLocator = page.locator('div[role="feed"]');
    onLog("Scrolling search feed to load listings...");

    let collectedUrls = new Set();
    let sameCountTicks = 0;
    let lastCollectedCount = 0;

    // Scroll loop to discover results
    while (collectedUrls.size < maxResults) {
      if (checkCancelled()) {
        onLog("Scraping cancelled during scroll phase.");
        break;
      }

      // Gather links containing /maps/place/
      const links = page.locator('div[role="feed"] a[href*="/maps/place/"]');
      const count = await links.count();

      for (let i = 0; i < count; i++) {
        const href = await links.nth(i).getAttribute('href');
        if (href) {
          // Normalize URL by removing search context parts if necessary
          collectedUrls.add(href);
        }
      }

      onLog(`Found ${collectedUrls.size} listings... (target: ${maxResults})`);

      if (collectedUrls.size >= maxResults) {
        break;
      }

      // Check if we hit the bottom
      if (collectedUrls.size === lastCollectedCount) {
        sameCountTicks++;
        if (sameCountTicks > 12) {
          onLog("Reached the end of the search results list.");
          break;
        }
      } else {
        sameCountTicks = 0;
      }
      lastCollectedCount = collectedUrls.size;

      // Scroll the container down
      await feedLocator.evaluate((el) => {
        el.scrollBy(0, el.scrollHeight);
      });

      // Randomized scroll wait to emulate human
      await page.waitForTimeout(1000 + Math.random() * 800);
    }

    const urlsToScrape = Array.from(collectedUrls).slice(0, maxResults);
    onLog(`Finished discovery. Scraping details for ${urlsToScrape.length} businesses...`);

    const scrapedLeads = [];
    for (let i = 0; i < urlsToScrape.length; i++) {
      if (checkCancelled()) {
        onLog("Scraping cancelled during detail scraping phase.");
        break;
      }

      const targetUrl = urlsToScrape[i];
      onLog(`[${i + 1}/${urlsToScrape.length}] Opening: ${targetUrl}`);

      try {
        // Navigate to the specific place detail URL
        await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
        // Small delay to let maps content render
        await page.waitForTimeout(1000 + Math.random() * 500);

        const lead = await scrapeCurrentPlace(page, targetUrl, onLog);
        scrapedLeads.push(lead);
        onLeadScraped(lead);
      } catch (err) {
        onLog(`Error scraping business details at index ${i + 1}: ${err.message}`);
      }

      onProgress(i + 1, urlsToScrape.length);
    }

    onLog(`Scraping complete. Successfully scraped ${scrapedLeads.length} leads.`);

  } catch (err) {
    onLog(`Fatal Scraper Error: ${err.message}`);
    throw err;
  } finally {
    onLog("Closing browser session...");
    await browser.close();
  }
}

/**
 * Cleans extracted text by stripping private-use unicode glyphs (Google Maps UI icons)
 */
function cleanField(val) {
  if (!val) return '';
  return val.replace(/[\uE000-\uF8FF]/g, '').trim();
}

/**
 * Parses details from an opened place page.
 */
async function scrapeCurrentPlace(page, url, onLog) {
  const data = {
    name: '',
    category: '',
    rating: 'N/A',
    reviewsCount: '0',
    address: 'Not available',
    phone: 'Not available',
    website: 'Not available',
    url: url
  };

  // 1. Business Name (h1 is highly standard)
  try {
    const h1Loc = page.locator('h1');
    await h1Loc.waitFor({ timeout: 5000 });
    data.name = cleanField(await h1Loc.first().innerText());
  } catch (err) {
    // fallback
    const title = await page.title();
    data.name = cleanField(title.split(' - ')[0] || 'Unknown Business');
  }

  // 2. Rating & Reviews
  try {
    const ratingContainer = page.locator('div.F7nice');
    if (await ratingContainer.count() > 0) {
      const text = await ratingContainer.first().innerText();
      const ratingMatch = text.match(/([0-9.]+)/);
      const reviewsMatch = text.match(/\(([0-9,]+)\)/);
      if (ratingMatch) data.rating = cleanField(ratingMatch[1]);
      if (reviewsMatch) data.reviewsCount = cleanField(reviewsMatch[1].replace(/,/g, ''));
    } else {
      const altRating = page.locator('span[aria-label*="stars"]');
      if (await altRating.count() > 0) {
        const label = await altRating.first().getAttribute('aria-label');
        const ratingMatch = label.match(/([0-9.]+)\s*stars/);
        const reviewsMatch = label.match(/([0-9,]+)\s*reviews/);
        if (ratingMatch) data.rating = cleanField(ratingMatch[1]);
        if (reviewsMatch) data.reviewsCount = cleanField(reviewsMatch[1].replace(/,/g, ''));
      }
    }
  } catch (e) {
    // ignore
  }

  // 3. Category
  try {
    const catLoc = page.locator('button[jsaction*="category"]');
    if (await catLoc.count() > 0) {
      data.category = cleanField(await catLoc.first().innerText());
    } else {
      // alt matchers
      const elements = page.locator('span:has-text("company"), span:has-text("developer"), span:has-text("contractor"), span:has-text("service"), span:has-text("agency")');
      const count = await elements.count();
      if (count > 0) {
        data.category = cleanField(await elements.first().innerText());
      }
    }
  } catch (e) {}

  // 4. Address
  try {
    const addressLoc = page.locator('button[data-item-id="address"]');
    if (await addressLoc.count() > 0) {
      data.address = cleanField(await addressLoc.first().innerText());
    } else {
      const altAddress = page.locator('button[aria-label*="Address:"]');
      if (await altAddress.count() > 0) {
        const text = await altAddress.first().getAttribute('aria-label');
        data.address = cleanField(text.replace('Address:', ''));
      }
    }
  } catch (e) {}

  // 5. Phone number
  try {
    const phoneLoc = page.locator('button[data-item-id^="phone:tel:"]');
    if (await phoneLoc.count() > 0) {
      data.phone = cleanField(await phoneLoc.first().innerText());
    } else {
      const altPhone = page.locator('button[aria-label*="Phone:"]');
      if (await altPhone.count() > 0) {
        const text = await altPhone.first().getAttribute('aria-label');
        data.phone = cleanField(text.replace('Phone:', ''));
      }
    }
  } catch (e) {}

  // 6. Website
  try {
    const webLoc = page.locator('a[data-item-id="authority"]');
    if (await webLoc.count() > 0) {
      data.website = await webLoc.first().getAttribute('href');
    } else {
      const altWeb = page.locator('a[aria-label*="Website:"]');
      if (await altWeb.count() > 0) {
        data.website = await altWeb.first().getAttribute('href');
      }
    }
  } catch (e) {}

  // 7. Scrape Email from Website
  data.email = 'Not available';
  if (data.website && data.website !== 'Not available' && data.website.startsWith('http')) {
    try {
      data.email = await extractEmailFromWebsite(data.website, onLog);
    } catch (err) {
      onLog(`Email scrape failed for ${data.website}: ${err.message}`);
    }
  }

  return data;
}

/**
 * Scrapes the target website to extract any publicly listed email address
 */
async function extractEmailFromWebsite(websiteUrl, onLog) {
  try {
    onLog(`Scanning company website for contact email: ${websiteUrl}`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000); // 6s limit
    
    const response = await fetch(websiteUrl, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
      }
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      return 'Not available';
    }
    
    const html = await response.text();
    let email = findEmailsInText(html);
    if (email) {
      onLog(`Found email on homepage: ${email}`);
      return email;
    }
    
    // Try contact page
    const contactLink = findContactPageLink(html, websiteUrl);
    if (contactLink) {
      onLog(`No email on homepage. Trying contact link: ${contactLink}`);
      const contactController = new AbortController();
      const contactTimeoutId = setTimeout(() => contactController.abort(), 6000);
      
      const contactResponse = await fetch(contactLink, {
        signal: contactController.signal,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
      });
      
      clearTimeout(contactTimeoutId);
      
      if (contactResponse.ok) {
        const contactHtml = await contactResponse.text();
        email = findEmailsInText(contactHtml);
        if (email) {
          onLog(`Found email on contact page: ${email}`);
          return email;
        }
      }
    }
    
    return 'Not available';
  } catch (err) {
    onLog(`Website contact scan failed: ${err.message}`);
    return 'Not available';
  }
}

/**
 * Regular expression helper to find emails in HTML text
 */
function findEmailsInText(text) {
  const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}/g;
  const matches = text.match(emailRegex);
  if (matches) {
    const forbiddenDomains = ['sentry.io', 'example.com', 'w3.org', 'domain.com', 'google.com'];
    const forbiddenExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
    
    for (const email of matches) {
      const lowerEmail = email.toLowerCase();
      const isImg = forbiddenExts.some(ext => lowerEmail.endsWith(ext));
      const isForbidden = forbiddenDomains.some(dom => lowerEmail.includes(dom));
      
      if (!isImg && !isForbidden) {
        return email;
      }
    }
  }
  return null;
}

/**
 * Search HTML for contact page links
 */
function findContactPageLink(html, baseUrl) {
  const contactRegex = /href="([^"]*contact[^"]*)"/i;
  const match = html.match(contactRegex);
  if (match) {
    let link = match[1];
    if (link.startsWith('/')) {
      try {
        const urlObj = new URL(baseUrl);
        return `${urlObj.origin}${link}`;
      } catch (e) {
        return null;
      }
    }
    if (link.startsWith('http')) {
      return link;
    }
  }
  return null;
}

module.exports = {
  runScraper
};
