// node worker/test_redirect.mjs : which addresses get forwarded, and where
import { canonical } from "./index.js";
const env = { CANONICAL_HOST: "climatetwins.org" };
for (const [m, u] of [["GET","http://climatetwins.org/"],["GET","http://climatetwins.org/methods.html#tropics"],["GET","https://www.climatetwins.org/?x=1"],
                      ["GET","https://climate-twins.forest4science.workers.dev/#Raleigh%2C%20NC"],["GET","https://climatetwins.org/data/na.dat?v=2026"],
                      ["POST","http://climatetwins.org/api/feedback"],["GET","http://localhost:8787/"]]) {
  const r = canonical(new URL(u), m, env);
  console.log(`${m.padEnd(4)} ${u.padEnd(64)} -> ${r ? r.status + " " + r.headers.get("location") : "served as is"}`);
}

// hardening headers: every response gets them, only pages get the policy
import { withHeaders, CSP } from "./index.js";
const page = withHeaders(new Response("<html>", { headers: { "content-type": "text/html; charset=utf-8" } }));
const data = withHeaders(new Response("{}", { headers: { "content-type": "application/json" } }));
console.log("page has CSP and nosniff:", page.headers.get("content-security-policy") === CSP && page.headers.get("x-content-type-options") === "nosniff");
console.log("data has nosniff, no CSP:", data.headers.get("x-content-type-options") === "nosniff" && !data.headers.get("content-security-policy"));
