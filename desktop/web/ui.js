/* AutoTessell — UI layer (vanilla, dependency-free).
 * Custom titlebar / window controls, resizable splitters + panel toggles,
 * 5-agent pipeline stepper, KPI count-up, toasts, keyboard shortcuts.
 * Exposes a global `UI`. Loaded before app.js; app.js calls into UI.*.
 */
(function (global) {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const AT = global.autotessell || null;
  const REDUCED = global.matchMedia
    ? global.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
  const root = document.documentElement;

  root.classList.toggle("is-electron", !!AT);

  // =====================================================================
  // Titlebar — window controls (Electron only)
  // =====================================================================
  function bindWindowControls() {
    if (!AT) return;
    const wc = AT.windowControls;
    const min = $("win-min"), max = $("win-max"), close = $("win-close");
    if (min) min.addEventListener("click", () => wc.minimize());
    if (max) max.addEventListener("click", () => wc.maximizeToggle());
    if (close) close.addEventListener("click", () => wc.close());
    if (wc.onMaximizedChange && max) {
      wc.onMaximizedChange((isMax) => {
        max.setAttribute("title", isMax ? "이전 크기로" : "최대화");
        max.setAttribute("aria-label", isMax ? "이전 크기로" : "최대화");
        max.classList.toggle("is-maximized", isMax);
      });
    }
  }

  // =====================================================================
  // Panel toggles + splitters (persisted)
  // =====================================================================
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, String(v)); } catch { /* ignore */ } },
  };

  function bindPanels() {
    const layout = document.querySelector(".layout");
    if (!layout) return;

    // restore widths
    const lw = parseInt(LS.get("at.ui.leftW", ""), 10);
    const rw = parseInt(LS.get("at.ui.rightW", ""), 10);
    if (lw >= 220 && lw <= 460) root.style.setProperty("--left-w", lw + "px");
    if (rw >= 220 && rw <= 460) root.style.setProperty("--right-w", rw + "px");
    if (LS.get("at.ui.leftCollapsed", "0") === "1") layout.classList.add("left-collapsed");
    if (LS.get("at.ui.rightCollapsed", "0") === "1") layout.classList.add("right-collapsed");
    syncToggleState(layout);

    const tl = $("toggle-left"), tr = $("toggle-right");
    if (tl) tl.addEventListener("click", () => {
      layout.classList.toggle("left-collapsed");
      LS.set("at.ui.leftCollapsed", layout.classList.contains("left-collapsed") ? "1" : "0");
      syncToggleState(layout); fireResize();
    });
    if (tr) tr.addEventListener("click", () => {
      layout.classList.toggle("right-collapsed");
      LS.set("at.ui.rightCollapsed", layout.classList.contains("right-collapsed") ? "1" : "0");
      syncToggleState(layout); fireResize();
    });

    bindSplitter($("split-left"), "--left-w", "at.ui.leftW", +1);
    bindSplitter($("split-right"), "--right-w", "at.ui.rightW", -1);
  }

  function syncToggleState(layout) {
    const tl = $("toggle-left"), tr = $("toggle-right");
    if (tl) tl.classList.toggle("active", !layout.classList.contains("left-collapsed"));
    if (tr) tr.classList.toggle("active", !layout.classList.contains("right-collapsed"));
  }

  function bindSplitter(el, cssVar, lsKey, sign) {
    if (!el) return;
    const clamp = (v) => Math.max(220, Math.min(460, v));
    const cur = () => parseInt(getComputedStyle(root).getPropertyValue(cssVar), 10) || 300;
    const apply = (v) => { const c = clamp(v); root.style.setProperty(cssVar, c + "px"); LS.set(lsKey, c); };
    let startX = 0, startW = 0, dragging = false;
    const onMove = (e) => { if (dragging) apply(startW + sign * (e.clientX - startX)); };
    const onUp = () => {
      dragging = false; el.classList.remove("dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      fireResize();
    };
    el.addEventListener("pointerdown", (e) => {
      dragging = true; startX = e.clientX; startW = cur();
      el.classList.add("dragging"); el.setPointerCapture && el.setPointerCapture(e.pointerId);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      e.preventDefault();
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") { apply(cur() - sign * 16); fireResize(); e.preventDefault(); }
      else if (e.key === "ArrowRight") { apply(cur() + sign * 16); fireResize(); e.preventDefault(); }
    });
    el.addEventListener("dblclick", () => { apply(cssVar === "--left-w" ? 300 : 320); fireResize(); });
    el.setAttribute("aria-valuenow", String(cur()));
  }

  let resizeRaf = 0;
  function fireResize() {
    cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  }

  // =====================================================================
  // Pipeline stepper (5-agent)
  // =====================================================================
  const STAGES = ["analyze", "preprocess", "strategize", "generate", "evaluate"];
  const stageOf = (msg, frac) => {
    const m = String(msg || "");
    if (/analyz|분석/i.test(m)) return "analyze";
    if (/preprocess|전처리/i.test(m)) return "preprocess";
    if (/strateg|전략/i.test(m)) return "strategize";
    if (/generat|경계층|\bBL\b|\btier\b|생성/i.test(m)) return "generate";
    if (/evaluat|평가|검증/i.test(m)) return "evaluate";
    const p = (frac || 0) * 100;
    if (p < 15) return "analyze";
    if (p < 35) return "preprocess";
    if (p < 45) return "strategize";
    if (p < 71) return "generate";
    return "evaluate";
  };
  function nodes() { return Array.from(document.querySelectorAll("#pipeline .pl-node")); }
  function setNode(node, cls) {
    node.classList.remove("idle", "active", "done", "fail", "warn");
    node.classList.add(cls);
    node.toggleAttribute("aria-current", cls === "active");
  }
  const Pipeline = {
    reset() {
      nodes().forEach((n) => setNode(n, "idle"));
      const rd = $("run-dock"); if (rd) rd.classList.remove("running");
    },
    update(frac, message) {
      const stage = stageOf(message, frac);
      const idx = STAGES.indexOf(stage);
      nodes().forEach((n) => {
        const i = STAGES.indexOf(n.dataset.stage);
        if (i < idx) setNode(n, "done");
        else if (i === idx) setNode(n, "active");
        else setNode(n, "idle");
      });
    },
    finish(verdict) {
      const ns = nodes();
      if (verdict === "PASS" || verdict === "PASS_WITH_WARNINGS") {
        ns.forEach((n) => setNode(n, "done"));
      } else if (verdict === "CANCELLED") {
        const a = ns.find((n) => n.classList.contains("active"));
        if (a) setNode(a, "warn");
      } else {
        const a = ns.find((n) => n.classList.contains("active"));
        if (a) setNode(a, "fail");
        else if (ns.length) setNode(ns[ns.length - 1], "fail");
      }
      const rd = $("run-dock"); if (rd) rd.classList.remove("running");
    },
  };

  // =====================================================================
  // KPI count-up
  // =====================================================================
  function countUp(el, value, opts) {
    if (!el) return;
    opts = opts || {};
    const dec = opts.decimals || 0;
    const suffix = opts.suffix || "";
    const fmt = opts.format || ((v) => v.toFixed(dec) + suffix);
    if (REDUCED) { el.textContent = fmt(value); return; }
    const from = parseFloat(String(el.textContent).replace(/[^0-9.\-]/g, "")) || 0;
    const t0 = performance.now(), dur = 600;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3); // ease-out cubic
      el.textContent = fmt(from + (value - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // =====================================================================
  // Toasts
  // =====================================================================
  function toast(kind, msg, opts) {
    opts = opts || {};
    const host = $("toasts");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    const body = document.createElement("div");
    body.className = "toast-body";
    if (opts.title) {
      const t = document.createElement("div"); t.className = "toast-title"; t.textContent = opts.title;
      body.appendChild(t);
    }
    const m = document.createElement("div"); m.className = "toast-msg"; m.textContent = msg;
    body.appendChild(m);
    if (opts.action && opts.onAction) {
      const b = document.createElement("button");
      b.className = "toast-action"; b.textContent = opts.action;
      b.addEventListener("click", () => { opts.onAction(); dismiss(); });
      body.appendChild(b);
    }
    el.appendChild(body);
    host.appendChild(el);

    let timer = 0;
    const dismiss = () => {
      clearTimeout(timer);
      el.classList.add("out");
      setTimeout(() => el.remove(), 220);
    };
    const arm = () => { timer = setTimeout(dismiss, opts.duration || 5000); };
    el.addEventListener("mouseenter", () => clearTimeout(timer));
    el.addEventListener("mouseleave", arm);
    arm();
    return dismiss;
  }

  // =====================================================================
  // Mesh reveal (fade + one-shot intro spin)
  // =====================================================================
  function meshReveal(viewer) {
    const gl = $("gl");
    if (gl) { gl.classList.remove("loaded"); void gl.offsetWidth; gl.classList.add("loaded"); }
    if (!REDUCED && viewer && typeof viewer.spinIntro === "function") viewer.spinIntro();
  }

  // =====================================================================
  // Keyboard shortcuts: F5 = Run, Esc = Stop
  // =====================================================================
  function bindShortcuts() {
    window.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test((e.target && e.target.tagName) || "");
      if (e.key === "F5") {
        e.preventDefault();
        const b = $("run-btn"); if (b && !b.disabled) b.click();
      } else if (e.key === "Escape" && !typing) {
        const b = $("stop-btn"); if (b && !b.disabled) b.click();
      }
    });
  }

  // =====================================================================
  // init
  // =====================================================================
  function init() {
    bindWindowControls();
    bindPanels();
    bindShortcuts();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.UI = {
    AT, REDUCED, pipeline: Pipeline, countUp, toast, meshReveal,
  };
})(window);
