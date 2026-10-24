# ADR 0010: Static security headers instead of nonce-based CSP

Status: accepted (2026-10-24)

## Context
Next.js documents a strict Content Security Policy with a per-request nonce set in `proxy.ts`. A nonce must be unique per request, so every page would have to be rendered dynamically on each request. VoltIA relies on prerendered pages with cached data (requirement NFR-02, first paint under 2.5 s, on a free hosting tier).

## Decision
Send a static CSP and the related headers from `next.config.ts`:

- `default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`.
- `connect-src 'self'` (the only network call from the browser is our own chat endpoint).
- `script-src 'self' 'unsafe-inline'` and `style-src 'self' 'unsafe-inline'`, because Next.js emits inline bootstrap scripts and ECharts sets inline styles.
- `Referrer-Policy: strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff`, `Permissions-Policy` with camera, microphone and geolocation disabled, and HSTS.

## Consequences
- The policy still blocks third-party scripts, framing, plugins, form posts to other origins and any network call except to our own origin.
- `'unsafe-inline'` for scripts weakens defence against injected inline script. This is accepted because the site has no accounts, no cookies, no stored user content and renders no HTML from users or from the model (chat output is rendered as text, never as HTML).
- A header test in the end-to-end suite pins the policy so it cannot loosen silently.

## Rejected alternatives
- Nonce-based strict CSP: forces dynamic rendering on every page and gives up prerendering.
- No CSP: leaves framing and third-party script injection open at no benefit.
