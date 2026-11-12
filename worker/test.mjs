// node worker/test.mjs : checks the request handler with a fake GitHub and a fake rate limiter
import assert from "node:assert/strict";
import { handleRequest } from "./index.js";
let sent = [], allow = true;
globalThis.fetch = async (url, init) => { sent.push({ url, body: JSON.parse(init.body), auth: init.headers.authorization }); return new Response(null, { status: 204 }); };
const env = { DISPATCH_TOKEN: "t0ken", GITHUB_REPO: "sequoia1997/climate-twins", REQUEST_LIMIT: { limit: async () => ({ success: allow }) } };
const post = (d, m = "POST") => handleRequest(new Request("https://x/api/request", { method: m, headers: { "CF-Connecting-IP": "1.2.3.4" }, body: m === "POST" ? JSON.stringify(d) : undefined }), env);
const out = async (label, p, want) => { const r = await p; console.log(label.padEnd(34), r.status, await r.text()); assert.equal(r.status, want, label); };
await out("normal request", post({ place: "Southport", region: "NC", note: "Hi <script>", elapsed: 9000 }), 200);
await out("bot filled hidden field", post({ place: "Spam", website: "http://x", elapsed: 9000 }), 200);
await out("sent too fast", post({ place: "Spam", elapsed: 300 }), 200);
await out("empty place", post({ place: " ", elapsed: 9000 }), 400);
allow = false; await out("rate limited", post({ place: "Durham", elapsed: 9000 }), 429); allow = true;
await out("GET", post(null, "GET"), 405);
await out("broken JSON", handleRequest(new Request("https://x/api/request", { method: "POST", body: "{nope" }), env), 400);
console.log("dispatches sent:", sent.length, JSON.stringify(sent[0]?.body), sent[0]?.url);
assert.equal(sent.length, 1, "only the normal request reaches GitHub");
assert.ok(!JSON.stringify(sent[0].body).includes("<script"), "angle brackets are stripped from the note");
console.log("all request checks passed");
