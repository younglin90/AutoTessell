/* AutoTessell — Electron main process.
 *
 * Wraps the existing FastAPI web GUI (desktop/server.py): detects a Python
 * interpreter, picks a free port, spawns `python -m desktop.server --port N`,
 * waits for /health, then loads http://127.0.0.1:N/ in a frameless window with
 * a custom titlebar. No third-party deps — Node/Electron built-ins only.
 */
"use strict";

const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net"); // port scanning (createServer)
const http = require("http"); // health check + export download (avoid net.fetch ambiguity)
const { spawn, spawnSync } = require("child_process");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let mainWin = null;
let splashWin = null;
let serverChild = null;
let serverPort = 0;
let cleanedUp = false;
const LOG_RING = []; // last 60 lines of server stdout/stderr
const HEALTH_BUDGET_MS = 90_000; // conda first-import can be slow
const APP_VERSION = require("./package.json").version;

function ringPush(line) {
  for (const l of String(line).split(/\r?\n/)) {
    if (!l) continue;
    LOG_RING.push(l);
    if (LOG_RING.length > 60) LOG_RING.shift();
  }
}

function logFilePath() {
  try {
    return path.join(app.getPath("userData"), "server.log");
  } catch {
    return path.join(app.getPath("temp"), "autotessell-server.log");
  }
}

function appendLog(text) {
  try {
    fs.appendFileSync(logFilePath(), text);
  } catch {
    /* best-effort */
  }
}

// ---------------------------------------------------------------------------
// Python interpreter resolution
// ---------------------------------------------------------------------------
function verifyPython(cand) {
  if (!cand) return false;
  try {
    const r = spawnSync(cand, ["--version"], { timeout: 8000, encoding: "utf8" });
    return r.status === 0 && /Python\s+3/.test((r.stdout || "") + (r.stderr || ""));
  } catch {
    return false;
  }
}

function registryInstallDir() {
  if (process.platform !== "win32") return null;
  try {
    const r = spawnSync(
      "reg",
      ["query", "HKCU\\Software\\AutoTessell", "/v", "InstallDir"],
      { encoding: "utf8", timeout: 6000 },
    );
    if (r.status !== 0) return null;
    const m = /InstallDir\s+REG_\w+\s+(.+)\s*$/m.exec(r.stdout || "");
    return m ? m[1].trim() : null;
  } catch {
    return null;
  }
}

function resolvePython() {
  const candidates = [];
  if (process.env.AUTOTESSELL_PYTHON) candidates.push(process.env.AUTOTESSELL_PYTHON);

  if (process.platform === "win32") {
    const localApp = process.env.LOCALAPPDATA;
    if (localApp) {
      candidates.push(
        path.join(localApp, "AutoTessell", "conda", "envs", "autotessell", "python.exe"),
      );
    }
    const instDir = registryInstallDir();
    if (instDir) {
      candidates.push(path.join(instDir, "conda", "envs", "autotessell", "python.exe"));
    }
    // PATH lookups (skip the Store alias stub).
    try {
      const w = spawnSync("where", ["python"], { encoding: "utf8", timeout: 6000 });
      if (w.status === 0) {
        for (const line of (w.stdout || "").split(/\r?\n/)) {
          const p = line.trim();
          if (p && !/\\Microsoft\\WindowsApps\\python(\.exe)?$/i.test(p)) candidates.push(p);
        }
      }
    } catch {
      /* ignore */
    }
    candidates.push("python.exe", "python");
  } else {
    candidates.push("python3", "python");
  }

  for (const c of candidates) {
    if (verifyPython(c)) return c;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Source root (contains the `desktop` package)
// ---------------------------------------------------------------------------
function hasServer(root) {
  try {
    return fs.existsSync(path.join(root, "desktop", "server.py"));
  } catch {
    return false;
  }
}

function resolveSrcRoot() {
  if (!app.isPackaged) {
    const dev = path.resolve(__dirname, "..", ".."); // desktop/electron -> repo root
    if (hasServer(dev)) return dev;
  }
  const instDir = registryInstallDir();
  if (instDir && hasServer(path.join(instDir, "src"))) return path.join(instDir, "src");
  const localApp = process.env.LOCALAPPDATA;
  if (localApp) {
    const guess = path.join(localApp, "AutoTessell", "src");
    if (hasServer(guess)) return guess;
  }
  // last resort: two levels up even if unverified
  return path.resolve(__dirname, "..", "..");
}

// ---------------------------------------------------------------------------
// Free port scan
// ---------------------------------------------------------------------------
function tryPort(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, "127.0.0.1");
  });
}

async function findFreePort(start, span) {
  for (let p = start; p < start + span; p++) {
    // eslint-disable-next-line no-await-in-loop
    if (await tryPort(p)) return p;
  }
  return start; // fall back — server will handle it
}

// ---------------------------------------------------------------------------
// Server spawn + health
// ---------------------------------------------------------------------------
function spawnServer(python, srcRoot, port) {
  const isUNC = srcRoot.startsWith("\\\\");
  // UNC mitigation: cmd/CreateProcess dislike UNC cwd. The server is
  // cwd-independent (all paths are Path(__file__)/tempfile), so run from temp
  // and inject the source root via PYTHONPATH.
  const cwd = isUNC ? app.getPath("temp") : srcRoot;
  const env = Object.assign({}, process.env, {
    PYTHONPATH: srcRoot + path.delimiter + (process.env.PYTHONPATH || ""),
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  });
  const child = spawn(python, ["-m", "desktop.server", "--port", String(port)], {
    cwd,
    env,
    shell: false, // never cmd.exe — it rejects UNC cwd
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const onData = (buf) => {
    const s = buf.toString();
    ringPush(s);
    appendLog(s);
  };
  child.stdout.on("data", onData);
  child.stderr.on("data", onData);
  return child;
}

function waitForHealth(port) {
  const deadline = Date.now() + HEALTH_BUDGET_MS;
  return new Promise((resolve, reject) => {
    const poll = () => {
      if (Date.now() > deadline) return reject(new Error("health timeout"));
      const req = http.get(
        { host: "127.0.0.1", port, path: "/health", timeout: 2500 },
        (res) => {
          if (res.statusCode !== 200) { res.resume(); return setTimeout(poll, 250); }
          let data = "";
          res.setEncoding("utf8");
          res.on("data", (c) => { data += c; });
          res.on("end", () => {
            try {
              const j = JSON.parse(data);
              if (j && j.status === "ok") {
                if (j.version && j.version !== APP_VERSION) {
                  ringPush(`[shell] server version ${j.version} != shell ${APP_VERSION}`);
                }
                return resolve(true);
              }
            } catch { /* not ready */ }
            setTimeout(poll, 250);
          });
        },
      );
      req.on("error", () => setTimeout(poll, 250));
      req.on("timeout", () => { req.destroy(); setTimeout(poll, 250); });
    };
    poll();
  });
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------
function createSplash() {
  splashWin = new BrowserWindow({
    width: 440,
    height: 300,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    transparent: false,
    backgroundColor: "#070a12",
    show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  splashWin.loadFile(path.join(__dirname, "splash.html"));
  splashWin.once("ready-to-show", () => splashWin && splashWin.show());
}

function splashStatus(text) {
  if (splashWin && !splashWin.isDestroyed()) {
    const safe = JSON.stringify(text);
    splashWin.webContents
      .executeJavaScript(`window.__setStatus && window.__setStatus(${safe})`)
      .catch(() => {});
  }
}

function createMainWindow(port) {
  mainWin = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    frame: false,
    backgroundColor: "#070a12",
    show: false,
    icon: path.join(__dirname, "assets", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  Menu.setApplicationMenu(null); // free F5/F11 for renderer shortcuts

  mainWin.loadURL(`http://127.0.0.1:${port}/`);
  mainWin.once("ready-to-show", () => {
    mainWin.show();
    if (splashWin && !splashWin.isDestroyed()) splashWin.close();
    splashWin = null;
  });
  const emitMax = () => {
    if (mainWin && !mainWin.isDestroyed()) {
      mainWin.webContents.send("win:maximized-changed", mainWin.isMaximized());
    }
  };
  mainWin.on("maximize", emitMax);
  mainWin.on("unmaximize", emitMax);
  mainWin.on("closed", () => {
    mainWin = null;
  });
}

// ---------------------------------------------------------------------------
// Fatal-error dialog
// ---------------------------------------------------------------------------
function showFatal(title, detail) {
  if (splashWin && !splashWin.isDestroyed()) splashWin.close();
  const buttons = ["다시 시도", "로그 폴더 열기", "종료"];
  const choice = dialog.showMessageBoxSync({
    type: "error",
    title: "AutoTessell",
    message: title,
    detail: (detail || "").slice(-1500),
    buttons,
    defaultId: 0,
    cancelId: 2,
  });
  if (choice === 0) {
    relaunchClean();
  } else if (choice === 1) {
    shell.showItemInFolder(logFilePath());
    app.quit();
  } else {
    app.quit();
  }
}

function relaunchClean() {
  cleanupServer();
  app.relaunch();
  app.exit(0);
}

// ---------------------------------------------------------------------------
// Cleanup — kill the server process tree (mesh engines spawn children)
// ---------------------------------------------------------------------------
function cleanupServer() {
  if (cleanedUp) return;
  cleanedUp = true;
  const child = serverChild;
  serverChild = null;
  if (!child || child.killed) return;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { timeout: 5000 });
    } else {
      child.kill("SIGTERM");
    }
  } catch {
    /* best-effort */
  }
}

// ---------------------------------------------------------------------------
// Boot sequence
// ---------------------------------------------------------------------------
async function boot() {
  createSplash();
  splashStatus("Python 인터프리터 탐지 중…");

  const python = resolvePython();
  if (!python) {
    showFatal(
      "Python 인터프리터를 찾을 수 없습니다",
      "다음 순서로 탐지했습니다:\n" +
        "  1. 환경변수 AUTOTESSELL_PYTHON\n" +
        "  2. %LOCALAPPDATA%\\AutoTessell\\conda\\envs\\autotessell\\python.exe\n" +
        "  3. PATH의 python\n\n" +
        "AutoTessell 본체(NSIS 설치본)를 먼저 설치하거나, " +
        "AUTOTESSELL_PYTHON 환경변수로 python.exe 경로를 지정하세요.",
    );
    return;
  }
  ringPush(`[shell] python = ${python}`);

  const srcRoot = resolveSrcRoot();
  if (!hasServer(srcRoot)) {
    showFatal(
      "AutoTessell 소스를 찾을 수 없습니다",
      `desktop/server.py 를 찾지 못했습니다 (검색 위치: ${srcRoot}).\n` +
        "AutoTessell 본체를 먼저 설치하세요.",
    );
    return;
  }
  ringPush(`[shell] srcRoot = ${srcRoot}`);

  serverPort = await findFreePort(9720, 20);
  splashStatus(`메쉬 서버 기동 중… (포트 ${serverPort})`);

  serverChild = spawnServer(python, srcRoot, serverPort);
  let earlyExit = false;
  serverChild.on("exit", (code, signal) => {
    if (!mainWin) {
      earlyExit = true;
      showFatal(
        "메쉬 서버가 기동 중 종료되었습니다",
        `exit code=${code} signal=${signal}\n\n` +
          "서버 로그 마지막 줄:\n" +
          LOG_RING.slice(-12).join("\n"),
      );
    }
  });

  splashStatus("서버 연결 확인 중…");
  try {
    await waitForHealth(serverPort);
  } catch (e) {
    if (!earlyExit) {
      showFatal(
        "메쉬 서버 응답이 없습니다 (시간 초과)",
        "서버 로그 마지막 줄:\n" + LOG_RING.slice(-15).join("\n"),
      );
    }
    return;
  }
  createMainWindow(serverPort);
}

// ---------------------------------------------------------------------------
// IPC — window controls, shell, export save
// ---------------------------------------------------------------------------
function registerIpc() {
  ipcMain.handle("win:minimize", () => mainWin && mainWin.minimize());
  ipcMain.handle("win:maximize-toggle", () => {
    if (!mainWin) return false;
    if (mainWin.isMaximized()) mainWin.unmaximize();
    else mainWin.maximize();
    return mainWin.isMaximized();
  });
  ipcMain.handle("win:close", () => mainWin && mainWin.close());
  ipcMain.handle("win:is-maximized", () => !!(mainWin && mainWin.isMaximized()));

  ipcMain.handle("shell:open-path", async (_e, p) => {
    if (!p) return "경로 없음";
    try {
      if (!fs.existsSync(p)) return "경로가 존재하지 않습니다";
      const stat = fs.statSync(p);
      if (stat.isDirectory()) return await shell.openPath(p);
      shell.showItemInFolder(p);
      return "";
    } catch (err) {
      return String(err);
    }
  });

  ipcMain.handle("export:save", async (_e, opts) => {
    try {
      const { url, filename } = opts || {};
      if (!url || !/^http:\/\/127\.0\.0\.1:/.test(url)) return { canceled: true, error: "잘못된 URL" };
      const res = await dialog.showSaveDialog(mainWin, {
        defaultPath: filename || "export.dat",
      });
      if (res.canceled || !res.filePath) return { canceled: true };
      await new Promise((resolve, reject) => {
        http.get(url, (resp) => {
          if (resp.statusCode !== 200) {
            resp.resume();
            return reject(new Error(`서버 ${resp.statusCode}`));
          }
          const out = fs.createWriteStream(res.filePath);
          resp.on("error", reject);
          out.on("error", reject);
          out.on("finish", resolve);
          resp.pipe(out);
        }).on("error", reject);
      });
      return { ok: true, path: res.filePath };
    } catch (err) {
      return { canceled: true, error: String(err) };
    }
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWin) {
      if (mainWin.isMinimized()) mainWin.restore();
      mainWin.focus();
    }
  });

  app.whenReady().then(() => {
    registerIpc();
    boot();
  });

  app.on("before-quit", cleanupServer);
  app.on("window-all-closed", () => {
    cleanupServer();
    app.quit();
  });
  process.on("exit", cleanupServer);
}
