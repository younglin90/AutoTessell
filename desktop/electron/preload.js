/* AutoTessell — Electron preload.
 * Exposes a minimal, safe API to the renderer via contextBridge.
 * The renderer checks `window.autotessell` to detect Electron; in a plain
 * browser it is undefined and the SPA falls back to window.open / no titlebar.
 */
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("autotessell", {
  platform: process.platform,
  versions: { electron: process.versions.electron },

  windowControls: {
    minimize: () => ipcRenderer.invoke("win:minimize"),
    maximizeToggle: () => ipcRenderer.invoke("win:maximize-toggle"),
    close: () => ipcRenderer.invoke("win:close"),
    isMaximized: () => ipcRenderer.invoke("win:is-maximized"),
    onMaximizedChange: (cb) =>
      ipcRenderer.on("win:maximized-changed", (_e, v) => cb(!!v)),
  },

  // p: absolute path to a directory (opens it) or file (reveals in folder).
  openResultsFolder: (p) => ipcRenderer.invoke("shell:open-path", p),

  // opts: { url: "http://127.0.0.1:PORT/...", filename: "mesh.vtu" }
  saveExport: (opts) => ipcRenderer.invoke("export:save", opts),
});
