// Serves site/dist under the base path, as GitHub Pages does. No dependency.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = "/TuxedoFinance/";
const root = join(fileURLToPath(new URL("..", import.meta.url)), "dist");
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".txt": "text/plain",
};

createServer((request, response) => {
  const path = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  let file = path.startsWith(BASE) ? join(root, normalize(path.slice(BASE.length))) : null;
  if (file && existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!file || !file.startsWith(root) || !existsSync(file)) {
    response.writeHead(404, { "Content-Type": types[".html"] });
    createReadStream(join(root, "404.html")).pipe(response);
    return;
  }
  response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(response);
}).listen(Number(process.argv[2]), "127.0.0.1");
