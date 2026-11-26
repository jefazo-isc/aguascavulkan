#!/usr/bin/env node
// ============================================================================
// StreetVulkan Web E2E smoke test (CI/CD)
// Serves the repository over HTTP, drives a headless Chrome through the
// DevTools Protocol (WebGL2 on SwiftShader, no GPU required) and checks that:
//   1. Sector (0, 0) GLB loads (no standalone fallback scene).
//   2. The city basemap fills the rest of Aguascalientes.
//   3. Road-graph traffic is running.
//   4. Teleports to Primer / Tercer Anillo land on the map.
// Screenshots and a JSON report are written to e2e-artifacts/ (CI artifact).
//
// Usage: node tests/e2e/smoke.mjs        (Node >= 22, or Node 20 with --experimental-websocket)
// Env:   CHROME_BIN=/path/to/chrome      E2E_TIMEOUT_MS=240000
//        E2E_CPU_THROTTLE=4  (emulate a slow CI runner locally)
// ============================================================================

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT_DIR = path.join(ROOT, 'e2e-artifacts');
const TIMEOUT_MS = Number(process.env.E2E_TIMEOUT_MS || 240000);
const CPU_THROTTLE = Number(process.env.E2E_CPU_THROTTLE || 1);
const IN_GITHUB = process.env.GITHUB_ACTIONS === 'true';
const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.json': 'application/json',
    '.wasm': 'application/wasm',
    '.wgsl': 'text/plain; charset=utf-8',
    '.glb': 'model/gltf-binary',
    '.bin': 'application/octet-stream',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function startStaticServer() {
    const server = http.createServer((req, res) => {
        const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        const filePath = path.normalize(path.join(ROOT, urlPath));
        if (!filePath.startsWith(ROOT)) {
            res.writeHead(403).end();
            return;
        }
        fs.stat(filePath, (err, st) => {
            if (err || !st.isFile()) {
                res.writeHead(404).end();
                return;
            }
            res.writeHead(200, {
                'Content-Type': MIME[path.extname(filePath)] || 'application/octet-stream',
                'Content-Length': st.size,
            });
            if (req.method === 'HEAD') res.end();
            else fs.createReadStream(filePath).pipe(res);
        });
    });
    return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

function findChrome() {
    const candidates = [process.env.CHROME_BIN, 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']
        .filter(Boolean);
    for (const c of candidates) {
        const r = spawnSync(c, ['--version'], { encoding: 'utf8' });
        if (r.status === 0) return { bin: c, version: r.stdout.trim() };
    }
    throw new Error('Chrome/Chromium not found (set CHROME_BIN)');
}

async function launchChrome(chromeBin) {
    const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sv-e2e-'));
    const proc = spawn(chromeBin, [
        '--headless=new',
        '--no-sandbox',
        '--no-first-run',
        '--use-angle=swiftshader',
        '--enable-unsafe-swiftshader',
        '--window-size=960,540',
        '--remote-debugging-port=0',
        `--user-data-dir=${userDataDir}`,
        'about:blank',
    ], { stdio: ['ignore', 'ignore', 'pipe'] });
    const wsUrl = await new Promise((resolve, reject) => {
        let buf = '';
        const timer = setTimeout(() => reject(new Error('Chrome did not expose DevTools in time')), 30000);
        proc.stderr.on('data', (d) => {
            buf += d.toString();
            const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
            if (m) {
                clearTimeout(timer);
                resolve(m[1]);
            }
        });
        proc.on('exit', (code) => reject(new Error(`Chrome exited early (${code})`)));
    });
    return { proc, port: new URL(wsUrl).port, userDataDir };
}

class CdpSession {
    constructor(wsUrl) {
        this.ws = new WebSocket(wsUrl);
        this.nextId = 0;
        this.pending = new Map();
        this.console = [];
        this.exceptions = [];
        this.ws.onmessage = (msg) => {
            const data = JSON.parse(msg.data);
            if (data.id && this.pending.has(data.id)) {
                this.pending.get(data.id)(data);
                this.pending.delete(data.id);
            } else if (data.method === 'Runtime.consoleAPICalled') {
                const text = data.params.args.map((a) => a.value ?? a.description ?? '').join(' ');
                this.console.push(`[${data.params.type}] ${text}`);
            } else if (data.method === 'Runtime.exceptionThrown') {
                const d = data.params.exceptionDetails;
                this.exceptions.push(d.exception?.description || d.text);
            }
        };
    }

    open() {
        return new Promise((resolve, reject) => {
            this.ws.onopen = resolve;
            this.ws.onerror = reject;
        });
    }

    send(method, params = {}) {
        return new Promise((resolve, reject) => {
            const id = ++this.nextId;
            this.pending.set(id, (d) => (d.error ? reject(new Error(`${method}: ${d.error.message}`)) : resolve(d.result)));
            this.ws.send(JSON.stringify({ id, method, params }));
        });
    }

    async evaluate(expression) {
        const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        return r.result.value;
    }

    async pressKey(code, key) {
        await this.send('Input.dispatchKeyEvent', { type: 'keyDown', code, key });
        await sleep(80);
        await this.send('Input.dispatchKeyEvent', { type: 'keyUp', code, key });
    }

    async screenshot(name) {
        const r = await this.send('Page.captureScreenshot', { format: 'png' });
        fs.writeFileSync(path.join(OUT_DIR, name), Buffer.from(r.data, 'base64'));
    }
}

const HUD_PROBE = `(() => {
    const t = (id) => (document.getElementById(id) || {}).textContent || '';
    return {
        loaderHidden: document.getElementById('loader-overlay')?.classList.contains('hidden') || false,
        loaderText: t('loader-text'),
        backend: t('hud-backend'),
        fps: t('hud-fps'),
        chunks: t('hud-chunks'),
        cars: t('hud-cars'),
        pos: t('hud-pos'),
    };
})()`;

async function waitFor(cdp, predicate, label, timeoutMs = TIMEOUT_MS) {
    const t0 = Date.now();
    let last = null;
    while (Date.now() - t0 < timeoutMs) {
        last = await cdp.evaluate(HUD_PROBE);
        if (predicate(last)) return { hud: last, ms: Date.now() - t0 };
        await sleep(500);
    }
    throw new Error(`Timeout waiting for ${label}. Last HUD: ${JSON.stringify(last)}`);
}

async function main() {
    if (typeof WebSocket === 'undefined') {
        throw new Error('Global WebSocket missing: use Node >= 22 or run with --experimental-websocket');
    }
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const report = { startedAt: new Date().toISOString(), checks: [], ok: false };
    const check = (name, pass, detail) => {
        report.checks.push({ name, pass: Boolean(pass), detail });
        console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
        if (!pass) throw new Error(`Check failed: ${name}`);
    };

    const chrome = findChrome();
    report.chrome = chrome.version;
    const server = await startStaticServer();
    const baseUrl = `http://127.0.0.1:${server.address().port}`;
    const browser = await launchChrome(chrome.bin);
    let cdp = null;
    try {
        const targets = await (await fetch(`http://127.0.0.1:${browser.port}/json`)).json();
        const page = targets.find((t) => t.type === 'page');
        cdp = new CdpSession(page.webSocketDebuggerUrl);
        await cdp.open();
        await cdp.send('Runtime.enable');
        await cdp.send('Page.enable');
        if (CPU_THROTTLE > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU_THROTTLE });
        await cdp.send('Page.navigate', { url: `${baseUrl}/web/index.html?backend=webgl2` });

        // 1-3. Initial load: GLB sector, basemap and traffic
        const boot = await waitFor(cdp, (h) => h.loaderHidden && /Sectores: 1/.test(h.chunks) &&
            (Number((h.chunks.match(/Mapa: (\d+)/) || [])[1]) >= 10) && /^\d+ FPS/.test(h.fps) &&
            Number.parseInt(h.cars, 10) > 0, 'sector + basemap + traffic');
        report.bootMs = boot.ms;
        report.hud = boot.hud;
        await sleep(1500);
        await cdp.screenshot('01_rolcar_sector_0_0.png');
        check('Backend WebGL2 activo', /WebGL2/.test(boot.hud.backend), boot.hud.backend);
        check('Sector 0,0 cargado sin escena de respaldo',
            !cdp.console.some((l) => /standalone fallback|Modo standalone/.test(l)), boot.hud.chunks);
        check('Mapa base de la ciudad construido', Number((boot.hud.chunks.match(/Mapa: (\d+)/) || [])[1]) >= 10, boot.hud.chunks);
        check('Tráfico sobre la red vial activo', Number.parseInt(boot.hud.cars, 10) >= 20, boot.hud.cars);

        // 4. Teleports
        await cdp.pressKey('Digit1', '1');
        const primer = await waitFor(cdp, (h) => /-1800\.0/.test(h.pos), 'Primer Anillo teleport', 60000);
        await sleep(2500);
        await cdp.screenshot('02_primer_anillo.png');
        check('Teleport Primer Anillo', true, primer.hud.pos);

        await cdp.pressKey('Digit3', '3');
        const tercer = await waitFor(cdp, (h) => /-7134\.0/.test(h.pos), 'Tercer Anillo teleport', 60000);
        await sleep(2500);
        await cdp.screenshot('03_tercer_anillo.png');
        check('Teleport Tercer Anillo', true, tercer.hud.pos);

        const fatal = cdp.exceptions.concat(cdp.console.filter((l) => /^\[error\]/.test(l)));
        check('Sin excepciones ni errores en consola', fatal.length === 0, fatal.slice(0, 3).join(' | '));
        report.ok = true;
    } finally {
        report.console = cdp ? cdp.console.slice(-50) : [];
        report.exceptions = cdp ? cdp.exceptions : [];
        report.finishedAt = new Date().toISOString();
        fs.writeFileSync(path.join(OUT_DIR, 'report.json'), JSON.stringify(report, null, 2));
        if (cdp) cdp.ws.close();
        server.close();
        // Wait for Chrome to exit before removing its profile: it keeps writing for a moment
        // after the kill, and a failing cleanup must not fail an otherwise green test.
        const exited = new Promise((r) => (browser.proc.exitCode !== null ? r() : browser.proc.once('exit', r)));
        browser.proc.kill('SIGKILL');
        await Promise.race([exited, sleep(5000)]);
        try {
            fs.rmSync(browser.userDataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
        } catch (err) {
            console.warn(`[e2e] could not remove ${browser.userDataDir}: ${err.message}`);
        }
    }
}

// GitHub Actions annotations are visible in the run summary (and through the public API)
const annotate = (level, title, msg) => {
    if (IN_GITHUB) console.log(`::${level} title=${title}::${String(msg).replace(/\r?\n/g, ' ').slice(0, 900)}`);
};

main().then(() => {
    console.log('E2E smoke test OK');
    annotate('notice', 'E2E smoke OK', 'Sector 0,0 + mapa base + tráfico + teleports verificados');
    process.exit(0);
}).catch((err) => {
    console.error(`E2E smoke test FAILED: ${err.message}`);
    annotate('error', 'E2E smoke FAILED', err.message);
    process.exit(1);
});
