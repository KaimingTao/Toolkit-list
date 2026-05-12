# sitemap-gen

Small Playwright-based crawler that visits pages on a single origin and prints a sitemap XML document.

## Environment Setup

1. Install Node.js 18 or newer.
2. Install project dependencies:

```bash
npm install
```

3. If Playwright asks for browser binaries, install them:

```bash
npx playwright install
```

## Usage

Run the crawler with an explicit start URL:

```bash
node crawl.js https://example.com > sitemap-output.txt
```

Without an argument, the script exits with:

```text
Usage: node crawl.js <start-url>
```

## Testing

Run the test suite with:

```bash
npm test
```

This uses Node.js's built-in test runner and executes `crawl.test.js`.

## Output

The script writes:

- crawled page URLs
- discovered URL patterns
- sitemap XML

Redirect output to a file if you want to keep the generated sitemap.
