/* Auto-Tessell Web GUI — controller.
 *
 * Talks to the FastAPI server (desktop/server.py) that serves this page:
 *   POST /upload                      → { job_id }
 *   GET  /jobs/{id}/surface           → STL (preview)
 *   WS   /ws/mesh/{id}                → live progress / result
 *   GET  /jobs/{id}/mesh              → { points, boundary_faces, patches }
 *   GET  /jobs/{id}/download/polyMesh.zip
 */
(function () {
  "use strict";

  const API = location.origin; // page is served by the same FastAPI server
  const WS_BASE = (location.protocol === "https:" ? "wss://" : "ws://") + location.host;
  const $ = (id) => document.getElementById(id);
  const UI = window.UI || {}; // ui.js layer (stepper/toast/countUp/meshReveal)
  const AT = window.autotessell || null; // Electron bridge (null in browser)
  const toast = UI.toast || function () {}; // no-op if ui.js absent

  const state = {
    jobId: null,
    fileName: null,
    surfaces: [],
    ws: null,
    running: false,
    surfaceBuf: null,
    resultMesh: null,
    viewMode: "surface",
    outputDir: null,
  };

  let viewer;
  try {
    viewer = new MeshViewer($("gl"));
    window.__viewer = viewer; // exposed for E2E pixel-probing / debugging
    window.__at = window.__at || {}; // E2E handles registered below
  } catch (e) {
    log("error", "WebGL 초기화 실패: " + e.message);
  }

  // ===================================================================
  // server health
  // ===================================================================
  let _wasConnected = true;
  async function pollHealth() {
    try {
      const r = await fetch(API + "/health", { cache: "no-store" });
      const j = await r.json();
      setServer(state.running ? "busy" : "on",
        state.running ? "메쉬 생성 중…" : "연결됨", j.version);
      _wasConnected = true;
    } catch {
      setServer("off", "서버 연결 안 됨", "");
      if (_wasConnected) { _wasConnected = false; toast("error", "메쉬 서버 연결이 끊겼습니다.", { title: "연결 끊김" }); }
    }
  }
  function setServer(kind, text, version) {
    const dot = $("server-dot");
    dot.className = "dot dot-" + kind;
    $("server-text").textContent = text;
    $("server-version").textContent = version ? "v" + version : "";
  }
  pollHealth();
  setInterval(pollHealth, 5000);

  // ===================================================================
  // segmented controls
  // ===================================================================
  function bindSeg(el, onChange) {
    el.setAttribute("role", "group");
    const btns = Array.from(el.querySelectorAll("button"));
    const activate = (b) => {
      if (b.disabled) return;
      btns.forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      el.dataset.value = b.dataset.v;
      if (onChange) onChange(b.dataset.v);
    };
    btns.forEach((b, i) => {
      b.addEventListener("click", () => activate(b));
      b.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        const step = e.key === "ArrowRight" ? 1 : btns.length - 1;
        let j = i;
        do {
          j = (j + step) % btns.length;
        } while (btns[j].disabled && j !== i);
        btns[j].focus();
        activate(btns[j]);
      });
    });
  }
  const QUALITY_HINTS = {
    draft: "draft · TetWild/Netgen · 빠른 검증 (~30초)",
    standard: "standard · Netgen/cfMesh · 엔지니어링 해석 (~수분)",
    fine: "fine · snappy + BL · 최종 CFD 제출용 (~30분+)",
  };
  // Selecting a mesh type defaults the tier to the matching NATIVE engine
  // (native-first policy); "Auto" hands the choice back to the strategist.
  // mesh_type 은 명시 선택 필수 (auto 제거 — index.html 의 주석 참고).
  const MESH_TYPE_DEFAULT_TIER = {
    tet: "native_tet",
    hex_dominant: "native_hex",
    poly: "native_poly",
  };
  bindSeg($("mesh-type"), (v) => {
    const t = MESH_TYPE_DEFAULT_TIER[v];
    if (t) $("tier").value = t;
  });
  bindSeg($("quality"), (v) => ($("quality-hint").textContent = QUALITY_HINTS[v] || ""));
  bindSeg($("boolean-operation"));
  bindSeg($("view-mode"), (v) => switchView(v));

  // ===================================================================
  // upload (drag-drop + click)
  // ===================================================================
  const dz = $("dropzone");
  const fileInput = $("file-input");
  dz.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFiles(fileInput.files);
    fileInput.value = ""; // allow re-selecting the same file
  });
  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.remove("drag");
    })
  );
  dz.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });

  // Multi-file entry point: the first file (when no job yet) creates the job
  // via /upload; every other file is added to that job as an extra surface.
  async function handleFiles(fileList) {
    const files = Array.from(fileList);
    if (!files.length) return;
    let start = 0;
    if (!state.jobId) {
      const ok = await uploadFile(files[0]);
      if (!ok) return; // first upload failed — nothing to attach to
      start = 1;
    }
    for (let i = start; i < files.length; i++) {
      await addSurface(files[i]);
    }
    await refreshSurfaces();
  }

  // -------------------------------------------------------------------
  // demo data — one-click sample meshes (fetched from the server, then
  // wrapped in a File and pushed through the normal upload path so the
  // preview + Run-enable flow is identical to a real drop).
  // -------------------------------------------------------------------
  (async function initDemos() {
    const row = $("demo-row");
    const chips = $("demo-chips");
    if (!row || !chips) return;
    let demos = [];
    try {
      const r = await fetch(API + "/demos", { cache: "no-store" });
      if (r.ok) demos = (await r.json()).demos || [];
    } catch { /* offline / no demos — leave hidden */ }
    if (!demos.length) return;
    chips.innerHTML = "";
    for (const d of demos) {
      const b = document.createElement("button");
      b.className = "demo-chip";
      b.type = "button";
      b.textContent = d.label;
      b.title = d.hint || d.name;
      b.addEventListener("click", () => loadDemo(d));
      chips.appendChild(b);
    }
    row.hidden = false;
  })();

  async function loadDemo(d) {
    const chips = $("demo-chips");
    if (chips) chips.querySelectorAll("button").forEach((b) => (b.disabled = true));
    log("info", `데모 로드: ${d.label}`);
    setProgress(0, "데모 불러오는 중…");
    try {
      const r = await fetch(`${API}/demos/${d.key}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`demo ${r.status}`);
      const blob = await r.blob();
      const file = new File([blob], d.name, { type: "application/octet-stream" });
      uploadFile(file); // reuses preview + Run-enable + toast path
    } catch (err) {
      setProgress(0, "대기 중");
      log("error", "데모 로드 실패: " + (err.message || err));
      toast("error", "데모를 불러오지 못했습니다", { title: "오류" });
    } finally {
      if (chips) chips.querySelectorAll("button").forEach((b) => (b.disabled = false));
    }
  }

  // Resolves to true on success (job created) / false on failure.
  function uploadFile(file) {
    return new Promise((resolve) => {
      log("info", `업로드 중: ${file.name} (${(file.size / 1024).toFixed(0)} KB)`);
      setProgress(0, "업로드 중…");
      const fd = new FormData();
      fd.append("file", file);
      // XHR (not fetch) so we get upload progress on large CAD files.
      const xhr = new XMLHttpRequest();
      xhr.open("POST", API + "/upload");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = (e.loaded / e.total) * 100;
          setProgress(pct, `업로드 중… ${Math.round(pct)}%`);
        }
      };
      xhr.onerror = () => {
        setProgress(0, "대기 중");
        log("error", "업로드 네트워크 오류");
        resolve(false);
      };
      xhr.onload = () => {
        setProgress(0, "대기 중");
        let j = {};
        try {
          j = JSON.parse(xhr.responseText);
        } catch {
          log("error", "업로드 응답 파싱 실패");
          resolve(false);
          return;
        }
        if (xhr.status !== 200) {
          log("error", "업로드 실패: " + (j.error || xhr.status));
          toast("error", j.error || `HTTP ${xhr.status}`, { title: "업로드 실패" });
          resolve(false);
          return;
        }
        state.jobId = j.job_id;
        state.fileName = j.filename;
        state.surfaces = [];
        state.resultMesh = null;
        state.faceMetrics = null;
        $("file-meta").classList.remove("hidden");
        $("file-meta").innerHTML = `job <code>${escapeHtml(j.job_id)}</code>`;
        $("run-btn").disabled = false;
        $("dl-zip").disabled = true;
        $("dl-export").disabled = true;
        const of = $("open-folder"); if (of) of.disabled = true;
        state.outputDir = null;
        $("kpi").classList.add("hidden");
        resultBtn().disabled = true;
        setNonOrthoAvailable(false);
        setView("surface");
        log("info", `업로드 완료 · job ${j.job_id}`);
        const dz = $("dropzone");
        if (dz && !UI.REDUCED) { dz.classList.remove("flash"); void dz.offsetWidth; dz.classList.add("flash"); }
        toast("ok", `${j.filename} (${(j.size / 1024).toFixed(0)} KB)`, { title: "업로드 완료" });
        refreshSurfaces();
        loadSurface();
        resolve(true);
      };
      xhr.send(fd);
    });
  }

  // ===================================================================
  // multi-surface (assembly) list — add / list / delete
  // ===================================================================
  async function addSurface(file) {
    if (!state.jobId) return false;
    log("info", `표면 추가: ${file.name} (${(file.size / 1024).toFixed(0)} KB)`);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch(`${API}/jobs/${state.jobId}/surfaces`, { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) {
        log("error", "표면 추가 실패: " + (j.error || r.status));
        toast("error", j.error || `HTTP ${r.status}`, { title: "표면 추가 실패" });
        return false;
      }
      log("info", `표면 추가됨 · ${j.surface ? j.surface.name : file.name} (총 ${j.n_surfaces}개)`);
      return true;
    } catch (e) {
      log("error", "표면 추가 네트워크 오류: " + e.message);
      return false;
    }
  }

  async function refreshSurfaces() {
    if (!state.jobId) { state.surfaces = []; renderSurfaces([]); return; }
    try {
      const r = await fetch(`${API}/jobs/${state.jobId}/surfaces`, { cache: "no-store" });
      const j = await r.json();
      state.surfaces = (j && j.surfaces) || [];
    } catch {
      /* keep previous list on transient error */
    }
    renderSurfaces(state.surfaces);
  }

  async function deleteSurface(surfaceId) {
    if (!state.jobId) return;
    try {
      const r = await fetch(`${API}/jobs/${state.jobId}/surfaces/${surfaceId}`, { method: "DELETE" });
      const j = await r.json();
      if (!r.ok) { log("warn", "표면 삭제 실패: " + (j.error || r.status)); return; }
      state.surfaces = (j && j.surfaces) || [];
      renderSurfaces(state.surfaces);
      log("info", `표면 삭제됨 (남은 ${j.n_surfaces}개)`);
    } catch (e) {
      log("warn", "표면 삭제 오류: " + e.message);
    }
  }

  function renderSurfaces(list) {
    const box = $("surface-list");
    const note = $("surface-note");
    if (!box) return;
    if (!list || !list.length) {
      box.classList.add("hidden");
      box.innerHTML = "";
      if (note) note.classList.add("hidden");
      setBooleanOperationVisible(false);
      // A job with no surfaces left cannot be meshed — keep Run disabled.
      if (state.jobId && !state.running) $("run-btn").disabled = true;
      return;
    }
    if (state.jobId && !state.running) $("run-btn").disabled = false;
    box.classList.remove("hidden");
    box.innerHTML = "";
    for (const s of list) {
      const item = document.createElement("div");
      item.className = "surface-item";

      const info = document.createElement("div");
      info.className = "surf-info";
      const nm = document.createElement("span");
      nm.className = "surf-name";
      nm.textContent = s.name;
      nm.title = s.filename;
      const meta = document.createElement("span");
      meta.className = "surf-meta";
      const kb = ((s.size_bytes || 0) / 1024).toFixed(0);
      meta.textContent = `${kb} KB` + (s.n_faces != null ? ` · ${Number(s.n_faces).toLocaleString()} faces` : "");
      info.appendChild(nm);
      info.appendChild(meta);

      const badges = document.createElement("div");
      badges.className = "surf-badges";
      if (s.watertight === true) {
        badges.appendChild(makeBadge("watertight", "surf-ok"));
      } else if (s.watertight === false) {
        badges.appendChild(makeBadge("open", "surf-bad"));
      } else if (s.error) {
        badges.appendChild(makeBadge("요약 불가", "surf-unknown"));
      }

      const del = document.createElement("button");
      del.className = "surf-del";
      del.type = "button";
      del.title = "표면 삭제";
      del.setAttribute("aria-label", `${s.name} 표면 삭제`);
      del.textContent = "✕";
      del.addEventListener("click", () => deleteSurface(s.surface_id));

      item.appendChild(info);
      item.appendChild(badges);
      item.appendChild(del);
      box.appendChild(item);
    }
    const hasBooleanInputs = list.length >= 2;
    setBooleanOperationVisible(hasBooleanInputs);
    if (note) {
      if (hasBooleanInputs) {
        note.classList.remove("hidden");
        note.textContent = `표면 ${list.length}개 · Native Tet boolean`;
      } else {
        note.classList.add("hidden");
      }
    }
  }

  function setBooleanOperationVisible(visible) {
    const wrap = $("boolean-operation-wrap");
    const seg = $("boolean-operation");
    if (!wrap || !seg) return;
    wrap.classList.toggle("hidden", !visible);
    if (visible) return;
    seg.dataset.value = "union";
    seg.querySelectorAll("button").forEach((button) => {
      button.classList.toggle("active", button.dataset.v === "union");
    });
  }

  function makeBadge(text, cls) {
    const b = document.createElement("span");
    b.className = "surf-badge " + cls;
    b.textContent = text;
    return b;
  }

  async function loadSurface() {
    if (!state.jobId || !viewer) return;
    try {
      const r = await fetch(`${API}/jobs/${state.jobId}/surface`, { cache: "no-store" });
      if (!r.ok) {
        // e.g. CAD upload with no tessellation backend → preview unavailable.
        let msg = `surface ${r.status}`;
        try { msg = (await r.json()).error || msg; } catch { /* non-JSON */ }
        log("info", "표면 미리보기 없음 — " + msg);
        $("vp-empty").textContent = "표면 미리보기를 사용할 수 없습니다. 메쉬를 생성하면 결과가 표시됩니다.";
        return;
      }
      const buf = await r.arrayBuffer();
      state.surfaceBuf = buf;
      if (state.viewMode === "surface") {
        viewer.setSTL(buf);
        setNonOrthoAvailable(false);
        applyColormap();
        $("vp-empty").classList.add("hidden");
        if (UI.meshReveal) UI.meshReveal(viewer);
      }
    } catch (e) {
      log("warn", "표면 미리보기 로드 실패: " + e.message);
    }
  }

  // ===================================================================
  // run / stop
  // ===================================================================
  $("run-btn").addEventListener("click", startMesh);
  $("stop-btn").addEventListener("click", stopMesh);

  function buildPayload() {
    const num = (id) => parseFloat($(id).value) || 0;
    const p = {
      action: "start",
      mesh_type: $("mesh-type").dataset.value,
      quality: $("quality").dataset.value,
      tier: $("tier").value,
      boolean_operation: $("boolean-operation").dataset.value || "union",
      max_iterations: parseInt($("max_iterations").value, 10) || 1,
    };
    if (num("max_cells") > 0) p.max_cells = parseInt($("max_cells").value, 10);
    if (num("bl_layers") > 0) p.bl_layers = parseInt($("bl_layers").value, 10);
    if (num("bl_growth_ratio") > 0) p.bl_growth_ratio = num("bl_growth_ratio");
    if (num("element_size") > 0) p.element_size = num("element_size");
    if (num("base_cell_size") > 0) p.base_cell_size = num("base_cell_size");
    ["repair_engine", "remesh_engine", "checker_engine", "postprocess_engine"].forEach((k) => {
      const v = $(k).value;
      if (v && v !== "auto" && v !== "none") p[k] = v;
      if (k === "postprocess_engine" && v === "none") p[k] = "none";
    });
    ["no_repair", "force_remesh", "allow_ai_fallback", "dry_run"].forEach((k) => {
      if ($(k).checked) p[k] = true;
    });
    return p;
  }

  function startMesh() {
    if (!state.jobId || state.running) return;
    const payload = buildPayload();
    state.running = true;
    $("run-btn").disabled = true;
    $("stop-btn").disabled = false;
    $("dl-zip").disabled = true;
    if (UI.pipeline) UI.pipeline.reset();
    $("run-dock").classList.add("running");
    setProgress(0, "연결 중…");
    setServer("busy", "메쉬 생성 중…", $("server-version").textContent.replace(/^v/, ""));
    log("info", `▶ 생성 시작 — mesh_type=${payload.mesh_type} quality=${payload.quality} tier=${payload.tier}`);

    const ws = new WebSocket(`${WS_BASE}/ws/mesh/${state.jobId}`);
    state.ws = ws;
    let opened = false;
    const connectTimer = setTimeout(() => {
      if (!opened && ws.readyState === WebSocket.CONNECTING) {
        log("error", "WebSocket 연결 시간 초과 (5s) — 서버 상태를 확인하세요.");
        try { ws.close(); } catch {}
      }
    }, 5000);
    ws.onopen = () => {
      opened = true;
      clearTimeout(connectTimer);
      ws.send(JSON.stringify(payload));
    };
    ws.onmessage = (ev) => {
      let m;
      try {
        m = JSON.parse(ev.data);
      } catch {
        log("warn", "잘못된 서버 메시지를 무시했습니다.");
        return;
      }
      handleMessage(m);
    };
    ws.onerror = () => log("error", "WebSocket 오류");
    ws.onclose = () => {
      clearTimeout(connectTimer);
      if (state.running) reconcileAfterClose();
    };
  }

  function stopMesh() {
    if (!state.jobId || !state.running) return;
    $("stop-btn").disabled = true;
    log("warn", "중지 요청 — 취소 중… (현재 단계가 끝나는 즉시 중단됩니다)");
    // Cooperative cancel: server sets the flag; the pipeline aborts at its next
    // progress step and sends a CANCELLED result, then the WS closes itself.
    fetch(`${API}/jobs/${state.jobId}/cancel`, { method: "POST" }).catch(() => {});
  }

  // WS closed without a terminal message — reconcile from the job's REST state.
  async function reconcileAfterClose() {
    log("warn", "WebSocket 연결 종료 — 작업 상태 확인 중…");
    try {
      const r = await fetch(`${API}/jobs/${state.jobId}`, { cache: "no-store" });
      const j = await r.json();
      state.running = false;
      finishRun();
      if (j.status === "completed") {
        const res = j.result || {};
        await onResult({ type: "result", success: true, verdict: res.verdict || "PASS", cells: res.cells, tier: res.tier });
      } else if (j.status === "cancelled") {
        setProgress(100, "취소됨");
        log("warn", "■ 취소됨");
      } else if (j.status === "failed") {
        log("error", "✘ 실패 — " + (j.error || "unknown"));
      } else {
        log("warn", `연결이 끊겼지만 작업이 백그라운드에서 계속될 수 있습니다 (status=${j.status}).`);
      }
    } catch (e) {
      state.running = false;
      finishRun();
      log("warn", "작업 상태 확인 실패: " + e.message);
    }
  }

  function finishRun() {
    $("run-btn").disabled = !state.jobId;
    $("stop-btn").disabled = true;
    pollHealth();
  }

  // ===================================================================
  // websocket message handling
  // ===================================================================
  function handleMessage(m) {
    switch (m.type) {
      case "progress":
        setProgress((m.progress || 0) * 100, m.message || m.stage || "");
        if (UI.pipeline) UI.pipeline.update(m.progress || 0, m.message || m.stage);
        break;
      case "log":
        log(m.level || "info", m.message || "");
        break;
      case "strategy":
        log("info", `전략: tier=${m.selected_tier} · mesh_type=${m.mesh_type || "-"} · cell=${(m.cell_size || 0).toFixed ? m.cell_size.toFixed(4) : m.cell_size}`);
        $("kpi-tier").textContent = m.selected_tier || "—";
        break;
      case "evaluation":
        updateKPI(m);
        break;
      case "result":
        onResult(m);
        break;
      case "error":
        log("error", "오류: " + (m.message || "unknown"));
        state.running = false;
        finishRun();
        $("run-dock").classList.remove("running");
        if (UI.pipeline) UI.pipeline.finish("ERROR");
        toast("error", m.message || "unknown", { title: "서버 오류" });
        break;
      default:
        break;
    }
  }

  function updateKPI(m) {
    $("kpi").classList.remove("hidden");
    if (m.verdict) {
      const v = $("kpi-verdict");
      if (v.textContent !== m.verdict) {
        v.textContent = m.verdict;
        v.className = "badge " + verdictClass(m.verdict);
        if (!UI.REDUCED) { v.classList.remove("pop"); void v.offsetWidth; v.classList.add("pop"); }
      }
    }
    if (m.tier) $("kpi-tier").textContent = m.tier;
    const cu = UI.countUp || ((el, val, o) => { if (el) el.textContent = (o && o.format ? o.format(val) : String(val)); });
    if (m.cells != null) cu($("kpi-cells"), Number(m.cells), { format: (v) => Math.round(v).toLocaleString() });
    if (m.max_non_ortho != null) cu($("kpi-nonortho"), Number(m.max_non_ortho), { decimals: 1, suffix: "°" });
    if (m.max_skewness != null) cu($("kpi-skew"), Number(m.max_skewness), { decimals: 2 });
    if (m.max_aspect_ratio != null) cu($("kpi-aspect"), Number(m.max_aspect_ratio), { decimals: 1 });
  }

  // Enriched KPI from /mesh?quality=1 stats: exact counts, min–max ranges,
  // and hover breakdowns (cell/face shapes + metric histograms).
  function renderKpiStats(s) {
    if (!s) return;
    const fmt = (n) => Number(n).toLocaleString();
    if (s.n_points != null) $("kpi-verts").textContent = fmt(s.n_points);
    if (s.n_cells != null) $("kpi-cells").textContent = fmt(s.n_cells);
    if (s.n_faces != null) $("kpi-faces").textContent = fmt(s.n_faces);

    const shapeTip = (el, shapes) => {
      if (!el || !shapes) return;
      const rows = Object.entries(shapes)
        .filter(([, n]) => n > 0)
        .sort((a, b) => b[1] - a[1])
        .map(([k, n]) => `<div class="tip-row"><span>${k.toUpperCase()}</span><b>${fmt(n)}</b></div>`)
        .join("");
      el.innerHTML = rows || '<div class="tip-row"><span>—</span></div>';
    };
    shapeTip($("tip-cells"), s.cell_shapes);
    shapeTip($("tip-faces"), s.face_shapes);

    const metric = (valEl, tipEl, h, opts) => {
      if (!valEl || !h) return;
      const d = opts.decimals;
      valEl.textContent =
        `${h.min.toFixed(d)}–${h.max.toFixed(d)}${opts.suffix || ""}`;
      if (!tipEl) return;
      const peak = Math.max.apply(null, h.counts) || 1;
      const bars = h.counts
        .map((c) => `<i style="height:${Math.max(3, Math.round((c / peak) * 100))}%"${c ? "" : ' class="z"'}></i>`)
        .join("");
      tipEl.innerHTML =
        `<div class="hist">${bars}</div>` +
        `<div class="hist-lbl"><span>${h.min.toFixed(d)}${opts.suffix || ""}</span>` +
        `<span>${h.max.toFixed(d)}${opts.suffix || ""}</span></div>`;
    };
    metric($("kpi-nonortho"), $("tip-nonortho"), s.non_ortho, { decimals: 1, suffix: "°" });
    metric($("kpi-skew"), $("tip-skew"), s.skewness, { decimals: 2 });
    metric($("kpi-aspect"), $("tip-aspect"), s.aspect_ratio, { decimals: 1 });
  }
  if (window.__at) window.__at.renderKpiStats = renderKpiStats; // E2E handle
  function verdictClass(v) {
    if (v === "PASS") return "pass";
    if (v === "PASS_WITH_WARNINGS" || v === "CANCELLED") return "warn";
    return "fail";
  }

  async function onResult(m) {
    state.running = false;
    finishRun();
    $("run-dock").classList.remove("running");
    if (m.output_dir) state.outputDir = m.output_dir;
    updateKPI(m);
    if (UI.pipeline) UI.pipeline.finish(m.verdict);
    if (m.verdict === "CANCELLED") {
      setProgress(100, "취소됨");
      log("warn", "■ 취소됨 — 사용자 요청으로 중단되었습니다.");
      toast("warn", "메쉬 생성이 취소되었습니다.");
      return; // no complete mesh to load
    }
    if (m.success) {
      setProgress(100, `완료! ${m.verdict || "PASS"}`);
      log("info", `✔ 완료 — ${m.verdict} · ${Number(m.cells || 0).toLocaleString()} cells · tier=${m.tier}`);
      toast("ok", `${Number(m.cells || 0).toLocaleString()} cells · ${m.tier || ""}`, { title: m.verdict || "PASS" });
    } else {
      setProgress(100, "실패");
      log("error", "✘ 실패 — " + (m.message || m.verdict || "FAIL"));
      toast("error", m.message || m.verdict || "FAIL", { title: "생성 실패" });
    }
    // A mesh may exist even when the verdict is FAIL (quality threshold miss).
    // If so, still let the user inspect & download it — matching the desktop GUI.
    const loaded = await loadResultMesh();
    if (loaded) {
      $("dl-zip").disabled = false;
      resultBtn().disabled = false;
      if (AT && state.outputDir) { const b = $("open-folder"); if (b) b.disabled = false; }
      setView("result");
      if (!m.success) log("warn", "FAIL 이지만 메쉬가 생성되어 뷰어/다운로드를 활성화했습니다.");
    }
  }

  // Pack the server's crinkle-slice data (cell centroids + per-face cell ids).
  function cellDataOf(j) {
    return j.cell_centroids ? {
      centroids: j.cell_centroids,
      boundaryCells: j.boundary_cells,
      internalOwner: j.internal_owner,
      internalNeighbour: j.internal_neighbour,
    } : null;
  }

  async function loadResultMesh() {
    if (!state.jobId || !viewer) return false;
    try {
      // quality=1 → per-boundary-face non-ortho/skewness; internal=1 → interior
      // faces so the slice/cutaway can reveal the volume cells.
      const r = await fetch(`${API}/jobs/${state.jobId}/mesh?quality=1&internal=1`, { cache: "no-store" });
      const j = await r.json();
      if (j.error || !j.points || !j.points.length) {
        if (j.error) log("warn", "결과 메쉬 없음: " + j.error);
        return false;
      }
      state.resultMesh = j;
      const fm = j.face_non_ortho
        ? { non_ortho: j.face_non_ortho, skewness: j.face_skewness }
        : null;
      state.faceMetrics = fm;
      viewer.setPolyMesh(j.points, j.boundary_faces, j.patches, fm, j.internal_faces || [], cellDataOf(j));
      setNonOrthoAvailable(viewer.hasFaceMetrics());
      setSliceAvailable(true, j.internal_available !== false && !!(j.internal_faces && j.internal_faces.length));
      renderKpiStats(j.stats);
      applyColormap();
      $("vp-empty").classList.add("hidden");
      $("dl-export").disabled = false;
      if (UI.meshReveal) UI.meshReveal(viewer);
      return true;
    } catch (e) {
      log("warn", "결과 메쉬 로드 오류: " + e.message);
      return false;
    }
  }

  // ===================================================================
  // viewport controls
  // ===================================================================
  $("colormap").addEventListener("change", applyColormap);
  $("wireframe").addEventListener("change", (e) => viewer && viewer.setWireframe(e.target.checked));
  $("reset-view").addEventListener("click", () => viewer && viewer.resetView());

  // ---- slice / cutaway controls ----
  $("slice-on").addEventListener("change", (e) => {
    if (!viewer) return;
    const on = e.target.checked;
    viewer.setSlice(on);
    $("slice-ctl").hidden = !on;
    if (on && !(viewer.hasInternalFaces && viewer.hasInternalFaces())) {
      log("info", "단면: 내부 면이 없어 경계면 컷어웨이로 표시합니다 (메쉬가 크거나 표면 뷰).");
    }
  });
  bindSeg($("slice-axis"), (v) => viewer && viewer.setSliceAxis(parseInt(v, 10)));
  $("slice-pos").addEventListener("input", (e) => viewer && viewer.setSlicePos(parseFloat(e.target.value)));
  $("slice-crinkle").addEventListener("change", (e) => viewer && viewer.setCrinkle(e.target.checked));
  $("slice-flip").addEventListener("click", () => {
    if (!viewer) return;
    viewer.setSliceFlip(!viewer.slice.flip);
  });

  // Slice only makes sense on a loaded volume result. Show/reset accordingly.
  function setSliceAvailable(show, hasInternal) {
    const grp = $("slice-group");
    if (!grp) return;
    grp.hidden = !show;
    if (!show) {
      // leaving result view → force slice off
      $("slice-on").checked = false;
      $("slice-ctl").hidden = true;
      if (viewer) viewer.setSlice(false);
    }
    grp.classList.toggle("slice-boundary-only", show && !hasInternal);
  }
  $("dl-zip").addEventListener("click", () => {
    if (!state.jobId) return;
    download(`${API}/jobs/${state.jobId}/download/polyMesh.zip`, `polyMesh_${state.jobId}.zip`);
  });
  $("dl-export").addEventListener("click", () => {
    if (!state.jobId) return;
    const fmt = $("export-format").value;
    const extMap = { vtu: "vtu", vtk: "vtk", fluent: "msh", cgns: "cgns", su2: "su2", nastran: "bdf", tecplot: "dat", stl: "stl", obj: "obj", ply: "ply" };
    log("info", `내보내기: ${fmt} …`);
    download(`${API}/jobs/${state.jobId}/export?format=${encodeURIComponent(fmt)}`, `mesh_${state.jobId}.${extMap[fmt] || fmt}`);
  });

  // Electron: native save dialog + streamed write; browser: window.open.
  async function download(url, filename) {
    if (AT && AT.saveExport) {
      const res = await AT.saveExport({ url, filename });
      if (res && res.ok) {
        toast("ok", filename, {
          title: "저장 완료", action: "폴더에서 보기",
          onAction: () => AT.openResultsFolder(res.path),
        });
      } else if (res && res.error) {
        toast("error", res.error, { title: "저장 실패" });
      }
    } else {
      window.open(url, "_blank");
    }
  }

  const openFolderBtn = $("open-folder");
  if (openFolderBtn) {
    openFolderBtn.addEventListener("click", async () => {
      if (!AT || !state.outputDir) return;
      const err = await AT.openResultsFolder(state.outputDir);
      if (err) toast("error", err, { title: "폴더 열기 실패" });
    });
  }
  const emptyOpen = $("vp-empty-open");
  if (emptyOpen) emptyOpen.addEventListener("click", () => $("file-input").click());

  function setNonOrthoAvailable(on) {
    const opt = $("colormap").querySelector('option[value="non-ortho"]');
    if (opt) opt.disabled = !on;
    // If non-ortho is selected but no longer available, fall back to solid.
    if (!on && $("colormap").value === "non-ortho") {
      $("colormap").value = "solid";
      applyColormap();
    }
  }

  function resultBtn() {
    return $("view-mode").querySelector('button[data-v="result"]');
  }
  function setView(v) {
    state.viewMode = v;
    $("view-mode").dataset.value = v;
    $("view-mode").querySelectorAll("button").forEach((b) =>
      b.classList.toggle("active", b.dataset.v === v)
    );
  }
  function switchView(v) {
    if (!viewer) return;
    state.viewMode = v;
    if (v === "surface" && state.surfaceBuf) {
      viewer.setSTL(state.surfaceBuf);
      setNonOrthoAvailable(false);
      setSliceAvailable(false);          // slice is a volume-result feature
    } else if (v === "result" && state.resultMesh) {
      const rm = state.resultMesh;
      viewer.setPolyMesh(
        rm.points, rm.boundary_faces, rm.patches,
        state.faceMetrics || null, rm.internal_faces || [], cellDataOf(rm)
      );
      setNonOrthoAvailable(viewer.hasFaceMetrics());
      setSliceAvailable(true, rm.internal_available !== false && !!(rm.internal_faces && rm.internal_faces.length));
    }
    applyColormap();
  }
  function applyColormap() {
    if (!viewer) return;
    const name = $("colormap").value;
    viewer.setColormap(name);
    const legend = $("legend");
    const labels = { aspect: "aspect", skewness: "skew", "non-ortho": "non-ortho" };
    if (labels[name]) {
      legend.classList.remove("hidden");
      $("legend-mid").textContent = labels[name];
    } else {
      legend.classList.add("hidden");
    }
  }

  // ===================================================================
  // progress + log
  // ===================================================================
  function setProgress(pct, label) {
    const clamped = Math.max(0, Math.min(100, pct));
    $("progress-bar").style.width = clamped + "%";
    if (label != null) $("progress-label").textContent = label;
    const track = document.querySelector(".progress-track");
    if (track) {
      track.setAttribute("aria-valuenow", String(Math.round(clamped)));
      // 0% while running (connecting/pre-analyze) → indeterminate sweep.
      track.classList.toggle("indeterminate", state.running && clamped <= 0.5);
    }
  }

  // Detail-log streaming (engine-level records, not just stage progress) can
  // emit hundreds of lines per run — log() must be O(1) per line (append one
  // DOM node), not rebuild the whole panel's innerHTML on every message.
  const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
  const LOG_CAP = 1000;
  const logEntries = [];
  let logEmptyEl = null; // "표시할 로그가 없습니다" placeholder, tracked to remove on first line
  $("log-filter").addEventListener("change", renderLog);

  function logPasses(entry) {
    const filter = $("log-filter").value;
    const min = filter === "all" ? -1 : LEVELS[filter] ?? -1;
    return (LEVELS[entry.level] ?? 1) >= min;
  }
  function logRow(entry) {
    const div = document.createElement("div");
    div.className = `l ${entry.level}`;
    div.textContent = entry.message;
    return div;
  }
  function log(level, message) {
    const entry = { level, message };
    logEntries.push(entry);
    const el = $("log");
    if (logEntries.length > LOG_CAP) {
      const evicted = logEntries.shift();
      if (logPasses(evicted)) el.querySelector(".l")?.remove();
    }
    if (logPasses(entry)) {
      if (logEmptyEl) { logEmptyEl.remove(); logEmptyEl = null; }
      el.appendChild(logRow(entry));
      el.scrollTop = el.scrollHeight;
    }
  }
  /** Full rebuild — only needed when the level filter dropdown changes. */
  function renderLog() {
    const el = $("log");
    const rows = logEntries.filter(logPasses);
    el.innerHTML = "";
    if (rows.length) {
      const frag = document.createDocumentFragment();
      for (const e of rows) frag.appendChild(logRow(e));
      el.appendChild(frag);
      logEmptyEl = null;
    } else {
      el.innerHTML = `<div class="log-empty">표시할 로그가 없습니다.</div>`;
      logEmptyEl = el.firstChild;
    }
    el.scrollTop = el.scrollHeight;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  log("info", "Auto-Tessell Web GUI 준비됨. 파일을 업로드하세요.");
})();
