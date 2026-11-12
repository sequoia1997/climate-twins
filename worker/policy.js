// The content security policy for every page. Kept in its own module: the Worker's main module may only export
// handlers (the Workers runtime refuses to start one that also exports a plain value), and the tests import it from here.
// Scripts run only from files on this site, the pinned map library on jsDelivr and Cloudflare's analytics: no inline script or
// inline event handler (tests/test_no_inline_scripts.py keeps it that way). 'inline-speculation-rules' allows only the pages'
// prerender hints, which are data, not code. Styles stay 'unsafe-inline' (the pages and the map set inline styles). The policy
// also blocks plugins, foreign forms, a changed base address and framing by other sites.
// Tested against the live pages (map, tiles, fonts, Wikimedia photos incl. their thumb.wikimedia.org redirect, the feedback form).
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'inline-speculation-rules' https://cdn.jsdelivr.net https://static.cloudflareinsights.com",
  "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  "img-src 'self' data: blob: https://commons.wikimedia.org https://upload.wikimedia.org https://thumb.wikimedia.org https://tiles.openfreemap.org",
  "connect-src 'self' https://species.climatetwins.org https://tiles.openfreemap.org https://cloudflareinsights.com",
  "worker-src 'self' blob:", "child-src 'self' blob:", "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'self'",
].join("; ");
