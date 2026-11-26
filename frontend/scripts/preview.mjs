import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = path.resolve("out");
const mime = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".ttf": "font/ttf", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8" };
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost");
    let file = path.resolve(root, "." + decodeURIComponent(url.pathname));
    if (file !== root && !file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    if ((await stat(file)).isDirectory()) file = path.join(file, "index.html");
    const body = await readFile(file);
    response.writeHead(200, { "Content-Type": mime[path.extname(file)] ?? "application/octet-stream" });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch { response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("Not found"); }
});
const port = Number(process.env.PORT ?? 3000);
server.listen(port, "127.0.0.1", () => console.log("Preview: http://127.0.0.1:" + port));
process.on("SIGINT", () => server.close());
process.on("SIGTERM", () => server.close());
