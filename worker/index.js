// Climate Twins Worker: serves the site from ./site and accepts place requests at POST /api/request.
// A request becomes a GitHub "repository_dispatch" event; the city-request workflow checks it against the data
// and opens an issue (which notifies the owner). Spam guards: a hidden field bots fill in, a minimum time on the
// form, a per-visitor rate limit, and length limits. Nothing personal is collected or stored.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/request") return handleRequest(request, env);
    return env.ASSETS.fetch(request);
  },
};

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
