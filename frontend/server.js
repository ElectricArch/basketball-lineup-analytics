const express = require('express');
const path = require('path');

const app = express();
const distPath = path.join(__dirname, 'dist', 'frontend', 'browser');
app.disable('x-powered-by');
app.use('/api', (_req, res) => res.status(404).json({ detail: 'No API is hosted by this frontend server.' }));
app.use((_req, res, next) => {
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  next();
});
app.use(express.static(distPath));
app.get(/.*/, (_req, res) => res.sendFile(path.join(distPath, 'index.html')));
app.use((_error, _req, res, _next) => res.status(500).json({ detail: 'Frontend content is unavailable.' }));
const port = Number(process.env.PORT || 4210);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT is invalid');
// The local validation harness supplies an explicit loopback bind address.
const host = process.env.HOST;
if (host && !require('net').isIP(host)) throw new Error('HOST must be a literal IP address');
app.listen(port, host);
