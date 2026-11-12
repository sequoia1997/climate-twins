// node worker/test_redirect.mjs : which addresses get forwarded, and where (fails with an error if anything is wrong)
import assert from "node:assert/strict";
import { canonical } from "./index.js";
const expect = {
  "GET http://climatetwins.org/": "301 https://climatetwins.org/",
  "GET http://climatetwins.org/methods.html#tropics": "301 https://climatetwins.org/methods.html#tropics",
  "GET https://www.climatetwins.org/?x=1": "301 https://climatetwins.org/?x=1",
  "GET https://climate-twins.forest4science.workers.dev/#Raleigh%2C%20NC": "301 https://climatetwins.org/#Raleigh%2C%20NC",
  "GET https://climatetwins.org/data/na.dat?v=2026": "served as is",
  "POST http://climatetwins.org/api/feedback": "served as is",
  "GET http://localhost:8787/": "served as is",
};
const env = { CANONICAL_HOST: "climatetwins.org" };
for (const [m, u] of [["GET","http://climatetwins.org/"],["GET","http://climatetwins.org/methods.html#tropics"],["GET","https://www.climatetwins.org/?x=1"],
                      ["GET","https://climate-twins.forest4science.workers.dev/#Raleigh%2C%20NC"],["GET","https://climatetwins.org/data/na.dat?v=2026"],
                      ["POST","http://climatetwins.org/api/feedback"],["GET","http://localhost:8787/"]]) {
  const r = canonical(new URL(u), m, env);
  const got = r ? r.status + " " + r.headers.get("location") : "served as is";
  console.log(`${m.padEnd(4)} ${u.padEnd(64)} -> ${got}`);
  assert.equal(got, expect[`${m} ${u}`], `${m} ${u}`);
}

// hardening headers: every response gets them, only pages get the policy
import { withHeaders } from "./index.js";
import { CSP } from "./policy.js";
const page = withHeaders(new Response("<html>", { headers: { "content-type": "text/html; charset=utf-8" } }));
const data = withHeaders(new Response("{}", { headers: { "content-type": "application/json" } }));
assert.ok(page.headers.get("content-security-policy") === CSP && page.headers.get("x-content-type-options") === "nosniff", "page has CSP and nosniff");
assert.ok(data.headers.get("x-content-type-options") === "nosniff" && !data.headers.get("content-security-policy"), "data has nosniff, no CSP");

// the _headers file served with the static assets must carry the same policy as the worker
import { readFileSync } from "node:fs";
const hf = readFileSync(new URL("../web/assets/_headers", import.meta.url), "utf8");
assert.ok(hf.includes("Content-Security-Policy: " + CSP) && hf.includes("X-Content-Type-Options: nosniff"), "_headers has the same policy as the Worker");

// the Workers runtime only accepts handlers as named exports of the main module
import * as main from "./index.js";
for (const [k, v] of Object.entries(main)) assert.ok(k === "default" || typeof v === "function", `index.js exports a non-function: ${k}`);
console.log("all redirect and header checks passed");
