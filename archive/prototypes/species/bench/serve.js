// HTTP/2 (TLS, self-signed) static server with Range support and a request log, used by bench.py.
// node serve.js ROOT PORT CERTDIR  ;  GET /__log returns and clears {n, bytes}
const http2 = require("http2"), fs = require("fs"), path = require("path");
const [root, port, certdir] = process.argv.slice(2);
const MIME = { ".html": "text/html", ".js": "text/javascript", ".png": "image/png", ".webp": "image/webp", ".json": "application/json",
  ".css": "text/css", ".pmtiles": "application/octet-stream", ".tif": "image/tiff", ".cts": "application/octet-stream", ".dat": "application/octet-stream" };
let log = { n: 0, bytes: 0, urls: [] };
const srv = http2.createSecureServer({ key: fs.readFileSync(certdir + "/k.pem"), cert: fs.readFileSync(certdir + "/c.pem"), allowHTTP1: true }, (req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  if (u === "/__log") { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(log)); log = { n: 0, bytes: 0, urls: [] }; return; }
  const f = path.join(root, u);
  if (!f.startsWith(path.resolve(root)) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; log.n++; log.urls.push(u + " 404"); res.end(); return; }
  const size = fs.statSync(f).size;
  const h = { "content-type": MIME[path.extname(f)] || "application/octet-stream", "accept-ranges": "bytes", "access-control-allow-origin": "*", "cache-control": "public, max-age=31536000, immutable" };
  let a = 0, b = size - 1, st = 200;
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
  if (m) { if (m[1] === "") { a = Math.max(0, size - +m[2]); } else { a = +m[1]; if (m[2]) b = Math.min(+m[2], size - 1); } st = 206; h["content-range"] = `bytes ${a}-${b}/${size}`; }
  h["content-length"] = b - a + 1;
  log.n++; log.bytes += b - a + 1; log.urls.push(u + (m ? ` [${a}-${b}]` : ""));
  res.writeHead(st, h);
  fs.createReadStream(f, { start: a, end: b }).pipe(res);
});
srv.listen(+port, () => console.log("listening", port));
