const RESOURCE_EXTENSIONS = new Set([
  ".pdf",
  ".zip",
  ".gz",
  ".tgz",
  ".tar",
  ".xml",
  ".json",
  ".csv",
  ".tsv",
  ".txt",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".svg",
  ".webp",
]);

function normalizeUrl(url) {
  const u = new URL(url);
  u.hash = "";
  u.searchParams.sort();
  return u.toString();
}

function isResourceUrl(url) {
  const { pathname, searchParams } = new URL(url);
  const lowerPath = pathname.toLowerCase();
  const extension = lowerPath.match(/\.[a-z0-9]+$/)?.[0];

  if (extension && RESOURCE_EXTENSIONS.has(extension)) {
    return true;
  }

  if (searchParams.has("resource")) {
    return true;
  }

  return lowerPath.includes("/download/");
}

function normalizePathSegment(segment) {
  if (/^\d+$/.test(segment)) {
    return ":num";
  }

  if (/^[0-9a-f]{8,}$/i.test(segment)) {
    return ":hex";
  }

  if (/^(?:19|20)\d{2}$/.test(segment)) {
    return ":year";
  }

  if (/\d/.test(segment) && /[a-z]/i.test(segment)) {
    return segment.replace(/\d+/g, ":num");
  }

  return segment;
}

function extractUrlPattern(url) {
  const parsed = new URL(url);
  const pathname = parsed.pathname
    .split("/")
    .filter(Boolean)
    .map(normalizePathSegment)
    .join("/");
  const queryKeys = [...parsed.searchParams.keys()].sort();
  const queryPattern = queryKeys.length ? `?${queryKeys.join("&")}` : "";

  return `${parsed.origin}/${pathname}${queryPattern}`;
}

function createCrawlerState(startUrl) {
  const normalizedStartUrl = normalizeUrl(startUrl);

  return {
    startUrl: normalizedStartUrl,
    visited: new Set(),
    queue: [normalizedStartUrl],
    queued: new Set([normalizedStartUrl]),
    edges: [],
    patternCounts: new Map(),
  };
}

function canFollowUrl(url, patternCounts, maxUrlsPerPattern = 10) {
  const pattern = extractUrlPattern(url);
  const count = patternCounts.get(pattern) || 0;
  return count < maxUrlsPerPattern;
}

function trackUrlPattern(url, patternCounts) {
  const pattern = extractUrlPattern(url);
  patternCounts.set(pattern, (patternCounts.get(pattern) || 0) + 1);
}

async function crawl(startUrl, options = {}) {
  const {
    sameOriginOnly = true,
    maxUrlsPerPattern = 10,
    browserFactory,
    logger = console.log,
    errorLogger = console.error,
  } = options;
  const state = createCrawlerState(startUrl);
  const makeBrowser = browserFactory || (async () => {
    const { chromium } = require("playwright");
    return chromium.launch();
  });
  const browser = await makeBrowser();
  const page = await browser.newPage();

  while (state.queue.length) {
    const current = normalizeUrl(state.queue.shift());
    state.queued.delete(current);
    if (state.visited.has(current)) continue;

    logger("Crawling:", current);
    state.visited.add(current);

    try {
      if (isResourceUrl(current)) {
        continue;
      }

      await page.goto(current, {
        waitUntil: "networkidle",
        timeout: 30000,
      });

      const links = await page.$$eval("a[href]", anchors =>
        anchors.map(a => a.href)
      );

      for (const link of links) {
        const normalized = normalizeUrl(link);

        if (
          sameOriginOnly &&
          new URL(normalized).origin !== new URL(state.startUrl).origin
        ) {
          continue;
        }

        state.edges.push([current, normalized]);

        if (
          !state.visited.has(normalized) &&
          !state.queued.has(normalized) &&
          !isResourceUrl(normalized) &&
          canFollowUrl(normalized, state.patternCounts, maxUrlsPerPattern)
        ) {
          trackUrlPattern(normalized, state.patternCounts);
          state.queued.add(normalized);
          state.queue.push(normalized);
        }
      }
    } catch (err) {
      errorLogger("Failed:", current, err.message);
    }
  }

  await browser.close();
  return state;
}

function printResults(state, logger = console.log) {
  logger("\nPages:");
  logger([...state.visited].join("\n"));

  logger("\nPatterns:");
  for (const [pattern, count] of state.patternCounts.entries()) {
    logger(`${count}\t${pattern}`);
  }

  logger("\nSitemap XML:");
  logger(`<?xml version="1.0" encoding="UTF-8"?>`);
  logger(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`);
  for (const url of state.visited) {
    logger(`  <url><loc>${url}</loc></url>`);
  }
  logger(`</urlset>`);
}

async function runCli(args = process.argv.slice(2)) {
  const inputUrl = args[0];

  if (!inputUrl) {
    console.error("Usage: node crawl.js <start-url>");
    return 1;
  }

  const state = await crawl(inputUrl);
  printResults(state);
  return 0;
}

if (require.main === module) {
  runCli().then(code => {
    process.exitCode = code;
  }).catch(err => {
    console.error(err);
    process.exitCode = 1;
  });
}

module.exports = {
  RESOURCE_EXTENSIONS,
  normalizeUrl,
  isResourceUrl,
  normalizePathSegment,
  extractUrlPattern,
  createCrawlerState,
  canFollowUrl,
  trackUrlPattern,
  crawl,
  printResults,
  runCli,
};
