// Climate Twins Worker: serves the site from ./site, accepts place requests at POST /api/request and private
// feedback at POST /api/feedback (emailed to the owner through Cloudflare Email Routing; never published).
// A request becomes a GitHub "repository_dispatch" event; the city-request workflow checks it against the data
// and opens an issue (which notifies the owner). Spam guards: a hidden field bots fill in, a minimum time on the
// form, a per-visitor rate limit, and length limits. Nothing personal is collected or stored.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const r = canonical(url, request.method, env);
    if (r) return r;
    if (url.pathname === "/api/request") return handleRequest(request, env);
    if (url.pathname === "/api/feedback") return handleFeedback(request, env);
    return env.ASSETS.fetch(request);
  },
};

// One address for everyone: https, no "www", and the old workers.dev address forwards to the domain.
// Only page loads (GET/HEAD) are redirected; form submissions are answered wherever they arrive.
export function canonical(url, method, env) {
  const home = env.CANONICAL_HOST;
  if (!home || (method !== "GET" && method !== "HEAD") || url.hostname === "localhost" || url.hostname === "127.0.0.1") return null;
  const wrongHost = url.hostname === "www." + home || url.hostname.endsWith(".workers.dev");
  if (url.protocol === "https:" && !wrongHost) return null;
  const to = new URL(url);
  to.protocol = "https:";
  if (wrongHost) to.hostname = home;
  return Response.redirect(to.toString(), 301);
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

const clean = (s, n) => String(s ?? "").normalize("NFC").replace(/[\u0000-\u001f\u007f<>`]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);

export async function handleRequest(request, env) {
  if (request.method !== "POST") return json({ error: "Use POST." }, 405);
  let data;
  try { data = await request.json(); } catch { return json({ error: "Could not read the request." }, 400); }
  // Bots: the hidden "website" field is filled in, or the form was sent implausibly fast. Answer as if it worked.
  if (data.website || (typeof data.elapsed === "number" && data.elapsed < 2500)) return json({ ok: true });
  const place = clean(data.place, 120), region = clean(data.region, 120), note = clean(data.note, 500);
  if (place.length < 2) return json({ error: "Please enter a place name." }, 400);
  if (env.REQUEST_LIMIT) {
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const { success } = await env.REQUEST_LIMIT.limit({ key: ip });
    if (!success) return json({ error: "Too many requests from here just now. Please try again in a minute." }, 429);
  }
  if (!env.DISPATCH_TOKEN || !env.GITHUB_REPO) return json({ error: "Requests aren't set up yet." }, 503);
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.DISPATCH_TOKEN}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "climate-twins-worker",
      "content-type": "application/json",
    },
    body: JSON.stringify({ event_type: "city-request", client_payload: { place, region, note } }),
  });
  if (!r.ok) return json({ error: "The request couldn't be sent right now. Please try again later." }, 502);
  return json({ ok: true });
}

// ---------------------------------------------------------------- feedback
const KINDS = { wrong: "Something looks wrong", bug: "Something's broken", idea: "Idea", other: "Other" };
const EMAIL_RE = /^[^\s@<>(),;:"\[\]\\]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$/;
const longText = (s, n) => String(s ?? "").normalize("NFC").replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "").trim().slice(0, n);

function b64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// A plain-text email, UTF-8, base64 body; every header value is validated or encoded, so nothing a visitor types
// can add headers.
export function buildFeedbackEmail({ from, to, replyTo, kind, message, context, repo }) {
  const first = message.replace(/\s+/g, " ").slice(0, 60);
  const subject = `[Climate Twins] ${KINDS[kind]}: ${first}${message.length > 60 ? "…" : ""}`;
  const issueBody = `${message}\n\n${context ? "---\n" + context : ""}`.slice(0, 6000);
  const issueLink = repo ? `https://github.com/${repo}/issues/new?labels=feedback&title=${encodeURIComponent(KINDS[kind] + ": " + first)}&body=${encodeURIComponent(issueBody)}` : "";
  const body = [
    `${KINDS[kind]}`, "", message, "",
    context ? "What they were looking at:\n" + context : "(They chose not to include what they were looking at.)", "",
    replyTo ? `Reply to: ${replyTo} (just hit Reply)` : "No reply address given.", "",
    issueLink ? "To track this publicly on GitHub (their email is not included):\n" + issueLink : "",
  ].join("\n");
  const headers = [
    `From: Climate Twins <${from}>`, `To: <${to}>`, replyTo ? `Reply-To: <${replyTo}>` : null,
    `Subject: =?UTF-8?B?${b64(subject)}?=`, `Message-ID: <${crypto.randomUUID()}@${from.split("@")[1]}>`,
    `Date: ${new Date().toUTCString()}`, "MIME-Version: 1.0", "Content-Type: text/plain; charset=UTF-8", "Content-Transfer-Encoding: base64",
  ].filter(Boolean);
  return headers.join("\r\n") + "\r\n\r\n" + b64(body).replace(/.{1,76}/g, "$&\r\n");
}

export async function handleFeedback(request, env) {
  if (request.method !== "POST") return json({ error: "Use POST." }, 405);
  let d;
  try { d = await request.json(); } catch { return json({ error: "Could not read the message." }, 400); }
  if (d.website || (typeof d.elapsed === "number" && d.elapsed < 3000)) return json({ ok: true });
  const kind = Object.hasOwn(KINDS, d.kind) ? d.kind : "other";
  const message = longText(d.message, 3000);
  const context = longText(d.context, 1200);
  const email = clean(d.email, 254);
  if (message.length < 3) return json({ error: "Please write a few words." }, 400);
  if (email && !EMAIL_RE.test(email)) return json({ error: "That email address doesn't look right. Leave it blank if you don't need a reply." }, 400);
  if (env.REQUEST_LIMIT) {
    const { success } = await env.REQUEST_LIMIT.limit({ key: "fb:" + (request.headers.get("CF-Connecting-IP") || "unknown") });
    if (!success) return json({ error: "Too many messages from here just now. Please try again in a minute." }, 429);
  }
  const alt = env.GITHUB_REPO ? `https://github.com/${env.GITHUB_REPO}/issues` : null;
  if (!env.FEEDBACK_MAIL || !env.FEEDBACK_TO || !env.FEEDBACK_FROM) return json({ error: "Feedback isn't set up yet.", alt }, 503);
  try {
    const EmailMessage = env.EmailMessage || (await import("cloudflare:email")).EmailMessage;
    const raw = buildFeedbackEmail({ from: env.FEEDBACK_FROM, to: env.FEEDBACK_TO, replyTo: email || null, kind, message, context, repo: env.GITHUB_REPO });
    await env.FEEDBACK_MAIL.send(new EmailMessage(env.FEEDBACK_FROM, env.FEEDBACK_TO, raw));
  } catch (e) {
    return json({ error: "Your message couldn't be sent right now. Please try again later.", alt }, 502);
  }
  return json({ ok: true });
}
