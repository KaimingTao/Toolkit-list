const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const {
  normalizeUrl,
  isResourceUrl,
  normalizePathSegment,
  extractUrlPattern,
  canFollowUrl,
  trackUrlPattern,
  crawl,
} = require("./crawl");

test("normalizeUrl removes hash and sorts query parameters", () => {
  assert.equal(
    normalizeUrl("https://example.com/path?b=2&a=1#section"),
    "https://example.com/path?a=1&b=2"
  );
});

test("isResourceUrl detects file extensions, downloads, and resource queries", () => {
  assert.equal(isResourceUrl("https://example.com/file.pdf"), true);
  assert.equal(isResourceUrl("https://example.com/reports/download/data"), true);
  assert.equal(isResourceUrl("https://example.com/page?resource=1"), true);
  assert.equal(isResourceUrl("https://example.com/page"), false);
});

test("normalizePathSegment generalizes dynamic-looking path segments", () => {
  assert.equal(normalizePathSegment("123"), ":num");
  assert.equal(normalizePathSegment("abcdef12"), ":hex");
  assert.equal(normalizePathSegment("2024"), ":num");
  assert.equal(normalizePathSegment("post123"), "post:num");
  assert.equal(normalizePathSegment("about"), "about");
});

test("extractUrlPattern normalizes path segments and query keys", () => {
  assert.equal(
    extractUrlPattern("https://example.com/posts/123?tag=js&sort=asc"),
    "https://example.com/posts/:num?sort&tag"
  );
});

test("trackUrlPattern and canFollowUrl enforce the per-pattern limit", () => {
  const patternCounts = new Map();
  const url = "https://example.com/posts/123";

  assert.equal(canFollowUrl(url, patternCounts, 2), true);
  trackUrlPattern(url, patternCounts);
  assert.equal(canFollowUrl(url, patternCounts, 2), true);
  trackUrlPattern(url, patternCounts);
  assert.equal(canFollowUrl(url, patternCounts, 2), false);
});

test("crawl filters cross-origin links, skips resources, and deduplicates URLs", async () => {
  const pages = new Map([
    ["https://example.com/", [
      "https://example.com/about",
      "https://example.com/about#team",
      "https://example.com/file.pdf",
      "https://other.example.org/offsite",
    ]],
    ["https://example.com/about", [
      "https://example.com/contact",
      "https://example.com/contact?b=2&a=1",
      "https://example.com/contact?a=1&b=2",
    ]],
    ["https://example.com/contact", []],
    ["https://example.com/contact?a=1&b=2", []],
  ]);

  const visitedByGoto = [];
  const browser = {
    async newPage() {
      return {
        async goto(url) {
          visitedByGoto.push(url);
          if (!pages.has(url)) {
            throw new Error(`Unexpected URL: ${url}`);
          }
        },
        async $$eval(selector, mapper) {
          assert.equal(selector, "a[href]");
          void mapper;
          return pages.get(visitedByGoto.at(-1));
        },
      };
    },
    async close() {},
  };

  const state = await crawl("https://example.com", {
    browserFactory: async () => browser,
    logger: () => {},
    errorLogger: () => {},
  });

  assert.deepEqual([...state.visited], [
    "https://example.com/",
    "https://example.com/about",
    "https://example.com/contact",
    "https://example.com/contact?a=1&b=2",
  ]);
  assert.deepEqual(visitedByGoto, [...state.visited]);
  assert.equal(state.edges.some(([, to]) => to === "https://other.example.org/offsite"), false);
  assert.equal(state.edges.some(([, to]) => to === "https://example.com/file.pdf"), true);
});

test("crawl logs navigation failures and continues", async () => {
  const pages = new Map([
    ["https://example.com/", [
      "https://example.com/fail",
      "https://example.com/success",
    ]],
    ["https://example.com/success", []],
  ]);
  const errors = [];
  let currentUrl = null;
  const browser = {
    async newPage() {
      return {
        async goto(url) {
          currentUrl = url;
          if (url === "https://example.com/fail") {
            throw new Error("boom");
          }
        },
        async $$eval() {
          return pages.get(currentUrl) || [];
        },
      };
    },
    async close() {},
  };

  const state = await crawl("https://example.com", {
    browserFactory: async () => browser,
    logger: () => {},
    errorLogger: (...args) => errors.push(args.join(" ")),
  });

  assert.deepEqual([...state.visited], [
    "https://example.com/",
    "https://example.com/fail",
    "https://example.com/success",
  ]);
  assert.equal(errors.length, 1);
  assert.match(errors[0], /Failed: https:\/\/example\.com\/fail boom/);
});

test("CLI exits with usage when start URL is missing", () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, "crawl.js")], {
    cwd: __dirname,
    encoding: "utf8",
  });

  assert.equal(result.status, 1);
  assert.match(result.stderr, /Usage: node crawl\.js <start-url>/);
});
