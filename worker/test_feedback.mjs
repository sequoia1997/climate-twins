// node worker/test_feedback.mjs : checks the feedback handler and the email it builds, with a fake mail binding
import { handleFeedback } from "./index.js";
const sent = []; let allow = true;
class FakeEmailMessage { constructor(from, to, raw) { Object.assign(this, { from, to, raw }); } }
const env = { FEEDBACK_MAIL: { send: async m => sent.push(m) }, FEEDBACK_TO: "owner@example.com", FEEDBACK_FROM: "feedback@climatetwins.org",
              GITHUB_REPO: "sequoia1997/climate-twins", EmailMessage: FakeEmailMessage, REQUEST_LIMIT: { limit: async () => ({ success: allow }) } };
const post = (d, e = env) => handleFeedback(new Request("https://x/api/feedback", { method: "POST", headers: { "CF-Connecting-IP": "1.2.3.4" }, body: JSON.stringify(d) }), e);
const show = async (label, p) => { const r = await p; console.log(label.padEnd(36), r.status, await r.text()); };
await show("normal, with reply address", post({ kind: "wrong", message: "Raleigh → Conway looks odd.\nÉté trop chaud?", email: "a.b@example.org", context: "Place: Raleigh, NC\nScenario: SSP2-4.5", elapsed: 9000 }));
await show("no email, no context", post({ kind: "idea", message: "Add snow please", elapsed: 9000 }));
await show("header injection attempt in email", post({ kind: "bug", message: "hi there", email: "x@y.com\r\nBcc: evil@z.com", elapsed: 9000 }));
await show("bad email", post({ kind: "bug", message: "hi there", email: "not-an-email", elapsed: 9000 }));
await show("too short", post({ kind: "bug", message: "!", elapsed: 9000 }));
await show("bot (hidden field)", post({ kind: "bug", message: "buy stuff", website: "x", elapsed: 9000 }));
await show("bot (too fast)", post({ kind: "bug", message: "buy stuff", elapsed: 500 }));
allow = false; await show("rate limited", post({ kind: "bug", message: "hello again", elapsed: 9000 })); allow = true;
await show("not set up yet", post({ kind: "bug", message: "hello", elapsed: 9000 }, { GITHUB_REPO: env.GITHUB_REPO }));
console.log("\nemails sent:", sent.length);
const raw = sent[0].raw, [head, body] = raw.split("\r\n\r\n");
console.log(head.split("\r\n").map(l => "  " + l).join("\n"));
const dec = s => new TextDecoder().decode(Uint8Array.from(atob(s), c => c.charCodeAt(0)));
console.log("  subject decoded:", dec(head.match(/Subject: =\?UTF-8\?B\?(.*)\?=/)[1]));
console.log("  body decoded:\n" + dec(body.replace(/\r\n/g, "")).split("\n").map(l => "    | " + l.slice(0, 110)).join("\n"));
console.log("  injection blocked:", !sent.some(m => /Bcc:/i.test(m.raw.split("\r\n\r\n")[0])), "| lines <= 998 chars:", raw.split("\r\n").every(l => l.length <= 998));
