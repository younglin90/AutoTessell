/* Auto-Tessell Web GUI — dependency-free WebGL mesh viewer.
 *
 * No three.js / no external libs (project policy: "외부 라이브러리에 의존하지
 * 않고 우리 코드로 직접 제작").  Renders triangle meshes (from STL surface
 * previews or polyMesh boundary faces) with flat shading, orbit/zoom/pan, a
 * wireframe overlay and a jet quality colormap that mirrors the Godot/Qt
 * viewer (non-ortho/85, skew/8, aspect (ar-1)/99).
 */
(function (global) {
  "use strict";

  // ----- tiny column-major mat4 helpers -----------------------------------
  const M4 = {
    perspective(fovy, aspect, near, far) {
      const f = 1 / Math.tan(fovy / 2);
      const nf = 1 / (near - far);
      // prettier-ignore
      return [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) * nf, -1,
        0, 0, 2 * far * near * nf, 0,
      ];
    },
    multiply(a, b) {
      const o = new Array(16);
      for (let c = 0; c < 4; c++) {
        for (let r = 0; r < 4; r++) {
          o[c * 4 + r] =
            a[0 * 4 + r] * b[c * 4 + 0] +
            a[1 * 4 + r] * b[c * 4 + 1] +
            a[2 * 4 + r] * b[c * 4 + 2] +
            a[3 * 4 + r] * b[c * 4 + 3];
        }
      }
      return o;
    },
    lookAt(eye, center, up) {
      const z = norm(sub(eye, center));
      const x = norm(cross(up, z));
      const y = cross(z, x);
      // prettier-ignore
      return [
        x[0], y[0], z[0], 0,
        x[1], y[1], z[1], 0,
        x[2], y[2], z[2], 0,
        -dot(x, eye), -dot(y, eye), -dot(z, eye), 1,
      ];
    },
  };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cross = (a, b) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const len = (a) => Math.hypot(a[0], a[1], a[2]);
  const norm = (a) => {
    const l = len(a) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  };

  // ----- jet colormap (blue=good → red=bad), mirrors quality_colormap.gd ---
  function jet(v) {
    v = Math.min(1, Math.max(0, v));
    if (v < 0.25) return [0, v / 0.25, 1];
    if (v < 0.5) return [0, 1, 1 - (v - 0.25) / 0.25];
    if (v < 0.75) return [(v - 0.5) / 0.25, 1, 0];
    return [1, 1 - (v - 0.75) / 0.25, 0];
  }
  const normNonOrtho = (d) => Math.min(1, Math.max(0, d / 85));
  const normSkew = (s) => Math.min(1, Math.max(0, s / 8));
  const normAspect = (a) => Math.min(1, Math.max(0, (a - 1) / 99));

  const VERT_SRC = `
    attribute vec3 aPos;
    attribute vec3 aNormal;
    attribute vec3 aColor;
    uniform mat4 uProj;
    uniform mat4 uView;
    varying vec3 vNormal;
    varying vec3 vColor;
    void main() {
      vNormal = aNormal;
      vColor = aColor;
      gl_Position = uProj * uView * vec4(aPos, 1.0);
    }`;
  const FRAG_SRC = `
    precision mediump float;
    varying vec3 vNormal;
    varying vec3 vColor;
    uniform vec3 uLightDir;
    uniform float uFlatLine;   // 0 = shaded faces, 1 = solid wire color
    void main() {
      vec3 n = normalize(vNormal);
      float diff = abs(dot(n, normalize(uLightDir)));
      float shade = 0.35 + 0.65 * diff;          // headlamp-ish
      vec3 c = mix(vColor * shade, vec3(0.05, 0.06, 0.09), uFlatLine);
      gl_FragColor = vec4(c, 1.0);
    }`;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      throw new Error("shader: " + gl.getShaderInfoLog(sh));
    }
    return sh;
  }

  class MeshViewer {
    constructor(canvas) {
      this.canvas = canvas;
      const gl =
        canvas.getContext("webgl", { antialias: true }) ||
        canvas.getContext("experimental-webgl");
      if (!gl) throw new Error("WebGL not available");
      this.gl = gl;
      this.prog = gl.createProgram();
      gl.attachShader(this.prog, compile(gl, gl.VERTEX_SHADER, VERT_SRC));
      gl.attachShader(this.prog, compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC));
      gl.linkProgram(this.prog);
      gl.useProgram(this.prog);
      this.loc = {
        aPos: gl.getAttribLocation(this.prog, "aPos"),
        aNormal: gl.getAttribLocation(this.prog, "aNormal"),
        aColor: gl.getAttribLocation(this.prog, "aColor"),
        uProj: gl.getUniformLocation(this.prog, "uProj"),
        uView: gl.getUniformLocation(this.prog, "uView"),
        uLightDir: gl.getUniformLocation(this.prog, "uLightDir"),
        uFlatLine: gl.getUniformLocation(this.prog, "uFlatLine"),
      };
      this.posBuf = gl.createBuffer();
      this.normBuf = gl.createBuffer();
      this.colorBuf = gl.createBuffer();
      this.lineBuf = gl.createBuffer();

      gl.enable(gl.DEPTH_TEST);
      // background from --bg-0 design token (fallback to the original value).
      let bg = [0.027, 0.039, 0.071];
      try {
        const hex = getComputedStyle(document.documentElement).getPropertyValue("--bg-0").trim();
        const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
        if (m) bg = [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
      } catch (e) { /* keep fallback */ }
      gl.clearColor(bg[0], bg[1], bg[2], 1.0);

      // camera (orbit) state
      this.az = 0.9;
      this.el = 0.5;
      this.dist = 3;
      this.target = [0, 0, 0];
      this.radius = 1;
      this.wireframe = false;
      this.colormap = "solid";

      this._mesh = null; // {points, faces}
      this._triCount = 0;
      this._lineCount = 0;

      this._bindControls();
      this._resize();
      window.addEventListener("resize", () => {
        this._resize();
        this.render();
      });
    }

    // ---- public API ------------------------------------------------------

    /**
     * points: [[x,y,z],...], faces: [[i,j,k,...polygon],...]
     * faceMetrics (optional): { non_ortho:[...], skewness:[...] } aligned to faces.
     */
    setPolyMesh(points, faces, patches, faceMetrics) {
      this._mesh = { points, faces, patches: patches || [] };
      this._faceMetrics = faceMetrics || null;
      this._buildPatchMap();
      this._buildGeometryCache(); // upload positions/normals/lines ONCE
      this._frameCamera();
      this.applyColormap(this.colormap); // only (re)builds the colour buffer
    }

    /** Replace mesh with a triangle soup parsed from an STL ArrayBuffer. */
    setSTL(arrayBuffer) {
      const { points, faces } = parseSTL(arrayBuffer);
      this.setPolyMesh(points, faces, [], null);
    }

    hasFaceMetrics() {
      return !!(this._faceMetrics && this._faceMetrics.non_ortho);
    }

    clear() {
      this._mesh = null;
      this._faceMetrics = null;
      this._triFace = null;
      this._triCount = 0;
      this._lineCount = 0;
      this.render();
    }

    setWireframe(on) {
      this.wireframe = !!on;
      this.render();
    }

    setColormap(name) {
      this.applyColormap(name);
    }

    resetView() {
      this.az = 0.9;
      this.el = 0.5;
      this._frameCamera();
      this.render();
    }

    /** One-shot intro spin: eases azimuth from an offset to its resting value.
     *  Cancels immediately on any user interaction (flag checked in controls). */
    spinIntro(ms) {
      if (!this._triCount) return;
      ms = ms || 1200;
      const target = this.az;
      const start = target - 0.9;
      const t0 = (typeof performance !== "undefined" ? performance.now() : Date.now());
      this._introActive = true;
      const step = (now) => {
        if (!this._introActive) return;
        const k = Math.min(1, (now - t0) / ms);
        const e = 1 - Math.pow(1 - k, 3);
        this.az = start + (target - start) * e;
        this.render();
        if (k < 1) requestAnimationFrame(step);
        else this._introActive = false;
      };
      requestAnimationFrame(step);
    }

    // ---- geometry / colors ----------------------------------------------

    _buildPatchMap() {
      // face index → patch index (for "patch" colormap)
      const m = this._mesh;
      m.facePatch = new Int32Array(m.faces.length).fill(-1);
      (m.patches || []).forEach((p, pi) => {
        const s = p.startFace | 0;
        const n = p.nFaces | 0;
        for (let i = s; i < s + n && i < m.faces.length; i++) m.facePatch[i] = pi;
      });
    }

    _frameCamera() {
      const pts = this._mesh.points;
      let lo = [Infinity, Infinity, Infinity];
      let hi = [-Infinity, -Infinity, -Infinity];
      for (const p of pts) {
        for (let k = 0; k < 3; k++) {
          if (p[k] < lo[k]) lo[k] = p[k];
          if (p[k] > hi[k]) hi[k] = p[k];
        }
      }
      this.target = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
      this.radius = Math.max(1e-6, len(sub(hi, lo)) / 2);
      this.dist = this.radius * 3.0;
    }

    /** Per-triangle scalar metrics computed from boundary-face geometry. */
    _triAspect(a, b, c) {
      const e0 = len(sub(b, a));
      const e1 = len(sub(c, b));
      const e2 = len(sub(a, c));
      const mn = Math.min(e0, e1, e2) || 1e-9;
      return Math.max(e0, e1, e2) / mn;
    }
    _triSkew(a, b, c) {
      // deviation of the triangle from equilateral, scaled toward checkMesh-ish
      // skewness units: 0 (perfect) .. larger (worse).
      const e0 = len(sub(b, a));
      const e1 = len(sub(c, b));
      const e2 = len(sub(a, c));
      const mean = (e0 + e1 + e2) / 3 || 1e-9;
      const dev = (Math.abs(e0 - mean) + Math.abs(e1 - mean) + Math.abs(e2 - mean)) / (3 * mean);
      return dev * 8; // map roughly into 0..8 skew band
    }

    /**
     * Build & upload positions/normals/wireframe-lines ONCE, and cache the
     * per-triangle metric arrays. Colormap switches only touch the colour
     * buffer (see applyColormap) — no geometry re-upload.
     */
    _buildGeometryCache() {
      const gl = this.gl;
      const m = this._mesh;
      const pos = [];
      const nrm = [];
      const lines = [];
      const triFace = []; // source polygon-face index per triangle
      const triAspect = [];
      const triSkew = [];

      for (let fi = 0; fi < m.faces.length; fi++) {
        const f = m.faces[fi];
        if (f.length < 3) continue;
        const v0 = m.points[f[0]];
        for (let t = 1; t < f.length - 1; t++) {
          const a = m.points[f[t]];
          const b = m.points[f[t + 1]];
          const n = norm(cross(sub(a, v0), sub(b, v0)));
          for (const p of [v0, a, b]) {
            pos.push(p[0], p[1], p[2]);
            nrm.push(n[0], n[1], n[2]);
          }
          triFace.push(fi);
          triAspect.push(this._triAspect(v0, a, b));
          triSkew.push(this._triSkew(v0, a, b));
        }
        for (let e = 0; e < f.length; e++) {
          const p = m.points[f[e]];
          const q = m.points[f[(e + 1) % f.length]];
          lines.push(p[0], p[1], p[2], q[0], q[1], q[2]);
        }
      }

      this._triCount = triFace.length;
      this._lineCount = lines.length / 3;
      this._triFace = triFace;
      this._triAspectArr = new Float32Array(triAspect);
      this._triSkewArr = new Float32Array(triSkew);

      gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pos), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(nrm), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.lineBuf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.STATIC_DRAW);
    }

    /** Recompute ONLY the colour buffer for the chosen colormap (cheap). */
    applyColormap(name) {
      this.colormap = name;
      if (!this._mesh || !this._triCount) {
        this.render();
        return;
      }
      const gl = this.gl;
      const fp = this._mesh.facePatch;
      const fm = this._faceMetrics;
      const base = [0.62, 0.66, 0.78];
      const palettePatch = (pi) => hsl((pi * 0.61803398875) % 1, 0.55, 0.6);

      const col = new Float32Array(this._triCount * 9); // 3 verts × rgb
      for (let t = 0; t < this._triCount; t++) {
        const fi = this._triFace[t];
        let c;
        if (name === "patch") {
          c = fp && fp[fi] >= 0 ? palettePatch(fp[fi]) : base;
        } else if (name === "aspect") {
          c = jet(normAspect(this._triAspectArr[t]));
        } else if (name === "skewness") {
          c = jet(normSkew(this._triSkewArr[t]));
        } else if (name === "non-ortho") {
          c = fm && fm.non_ortho && fm.non_ortho[fi] != null
            ? jet(normNonOrtho(fm.non_ortho[fi]))
            : base;
        } else {
          c = base;
        }
        const o = t * 9;
        col[o] = c[0]; col[o + 1] = c[1]; col[o + 2] = c[2];
        col[o + 3] = c[0]; col[o + 4] = c[1]; col[o + 5] = c[2];
        col[o + 6] = c[0]; col[o + 7] = c[1]; col[o + 8] = c[2];
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuf);
      gl.bufferData(gl.ARRAY_BUFFER, col, gl.STATIC_DRAW);
      this.render();
    }

    // ---- render ----------------------------------------------------------

    _resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = this.canvas.clientWidth || 600;
      const h = this.canvas.clientHeight || 400;
      this.canvas.width = Math.floor(w * dpr);
      this.canvas.height = Math.floor(h * dpr);
      this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    }

    _eye() {
      const ce = Math.cos(this.el),
        se = Math.sin(this.el),
        ca = Math.cos(this.az),
        sa = Math.sin(this.az);
      return [
        this.target[0] + this.dist * ce * ca,
        this.target[1] + this.dist * se,
        this.target[2] + this.dist * ce * sa,
      ];
    }

    render() {
      const gl = this.gl;
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      if (!this._triCount) return;
      const aspect = this.canvas.width / Math.max(1, this.canvas.height);
      const proj = M4.perspective(Math.PI / 4, aspect, this.radius * 0.01, this.dist * 10 + this.radius * 10);
      const eye = this._eye();
      const view = M4.lookAt(eye, this.target, [0, 1, 0]);
      gl.useProgram(this.prog);
      gl.uniformMatrix4fv(this.loc.uProj, false, new Float32Array(proj));
      gl.uniformMatrix4fv(this.loc.uView, false, new Float32Array(view));
      const ld = norm(sub(eye, this.target));
      gl.uniform3f(this.loc.uLightDir, ld[0], ld[1], ld[2]);

      // faces
      gl.uniform1f(this.loc.uFlatLine, 0.0);
      this._bindAttr(this.posBuf, this.loc.aPos);
      this._bindAttr(this.normBuf, this.loc.aNormal);
      this._bindAttr(this.colorBuf, this.loc.aColor);
      gl.drawArrays(gl.TRIANGLES, 0, this._triCount);

      // wireframe overlay
      if (this.wireframe && this._lineCount) {
        gl.uniform1f(this.loc.uFlatLine, 1.0);
        this._bindAttr(this.lineBuf, this.loc.aPos);
        // normals/colors irrelevant for lines but attrs must be enabled
        this._bindAttr(this.lineBuf, this.loc.aNormal);
        this._bindAttr(this.lineBuf, this.loc.aColor);
        gl.drawArrays(gl.LINES, 0, this._lineCount);
      }
    }

    _bindAttr(buf, loc) {
      const gl = this.gl;
      if (loc < 0) return;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0);
    }

    // ---- mouse / touch orbit --------------------------------------------

    _bindControls() {
      const c = this.canvas;
      let dragging = false;
      let panning = false;
      let lx = 0,
        ly = 0;
      const down = (e) => {
        this._introActive = false; // cancel intro spin on interaction
        dragging = true;
        panning = e.button === 2 || e.shiftKey;
        lx = e.clientX;
        ly = e.clientY;
        e.preventDefault();
      };
      const move = (e) => {
        if (!dragging) return;
        const dx = e.clientX - lx;
        const dy = e.clientY - ly;
        lx = e.clientX;
        ly = e.clientY;
        if (panning) {
          const k = this.dist * 0.0015;
          const eye = this._eye();
          const fwd = norm(sub(this.target, eye));
          const right = norm(cross(fwd, [0, 1, 0]));
          const up = cross(right, fwd);
          for (let i = 0; i < 3; i++)
            this.target[i] += (-dx * right[i] + dy * up[i]) * k;
        } else {
          this.az += dx * 0.01;
          this.el += dy * 0.01;
          const lim = Math.PI / 2 - 0.02;
          this.el = Math.max(-lim, Math.min(lim, this.el));
        }
        this.render();
      };
      const up = () => {
        dragging = false;
        panning = false;
      };
      c.addEventListener("mousedown", down);
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
      c.addEventListener("contextmenu", (e) => e.preventDefault());
      c.addEventListener(
        "wheel",
        (e) => {
          e.preventDefault();
          // Normalise deltaMode: 0=pixel, 1=line (~16px), 2=page (~viewport).
          const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? this.canvas.clientHeight : 1;
          this._zoom(e.deltaY * unit * 0.001);
        },
        { passive: false }
      );

      // ---- touch: one finger orbit, two fingers pan + pinch-zoom ----------
      let touchMode = 0; // 1=orbit, 2=pan/zoom
      let tPrev = null;
      let pinchPrev = 0;
      const touchMid = (t) => [
        (t[0].clientX + t[1].clientX) / 2,
        (t[0].clientY + t[1].clientY) / 2,
      ];
      const pinchDist = (t) =>
        Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
      c.addEventListener("touchstart", (e) => {
        e.preventDefault();
        this._introActive = false;
        if (e.touches.length === 1) {
          touchMode = 1;
          tPrev = [e.touches[0].clientX, e.touches[0].clientY];
        } else if (e.touches.length >= 2) {
          touchMode = 2;
          tPrev = touchMid(e.touches);
          pinchPrev = pinchDist(e.touches);
        }
      }, { passive: false });
      c.addEventListener("touchmove", (e) => {
        e.preventDefault();
        if (touchMode === 1 && e.touches.length === 1) {
          const x = e.touches[0].clientX, y = e.touches[0].clientY;
          this.az += (x - tPrev[0]) * 0.01;
          this.el += (y - tPrev[1]) * 0.01;
          const lim = Math.PI / 2 - 0.02;
          this.el = Math.max(-lim, Math.min(lim, this.el));
          tPrev = [x, y];
          this.render();
        } else if (touchMode === 2 && e.touches.length >= 2) {
          const mid = touchMid(e.touches);
          const k = this.dist * 0.0015;
          const eye = this._eye();
          const fwd = norm(sub(this.target, eye));
          const right = norm(cross(fwd, [0, 1, 0]));
          const up2 = cross(right, fwd);
          const dx = mid[0] - tPrev[0], dy = mid[1] - tPrev[1];
          for (let i = 0; i < 3; i++)
            this.target[i] += (-dx * right[i] + dy * up2[i]) * k;
          const pd = pinchDist(e.touches);
          if (pinchPrev > 0) this._zoom((pinchPrev - pd) * 0.005);
          pinchPrev = pd;
          tPrev = mid;
          this.render();
        }
      }, { passive: false });
      c.addEventListener("touchend", () => { touchMode = 0; });
    }

    _zoom(delta) {
      this._introActive = false;
      const f = Math.exp(delta);
      this.dist = Math.max(this.radius * 0.05, this.dist * f);
      this.render();
    }
  }

  // ----- STL parser (binary + ASCII) -> dedup points + triangle faces ------
  function parseSTL(buf) {
    const view = new DataView(buf);
    const u8 = new Uint8Array(buf);
    // ASCII detection: starts with "solid" AND no obviously-binary tri count match
    let isAscii = false;
    if (u8.length > 5) {
      const head = String.fromCharCode(u8[0], u8[1], u8[2], u8[3], u8[4]).toLowerCase();
      if (head === "solid") {
        // binary files sometimes start with "solid" too; verify size
        if (buf.byteLength >= 84) {
          const nTri = view.getUint32(80, true);
          const expected = 84 + nTri * 50;
          isAscii = expected !== buf.byteLength;
        } else {
          isAscii = true;
        }
      }
    }
    const points = [];
    const faces = [];
    const map = new Map();
    const key = (x, y, z) => x.toFixed(5) + "," + y.toFixed(5) + "," + z.toFixed(5);
    const addPt = (x, y, z) => {
      const k = key(x, y, z);
      let id = map.get(k);
      if (id === undefined) {
        id = points.length;
        points.push([x, y, z]);
        map.set(k, id);
      }
      return id;
    };

    if (isAscii) {
      const text = new TextDecoder().decode(buf);
      const re = /vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)/g;
      const vs = [];
      let m;
      while ((m = re.exec(text))) {
        vs.push(addPt(parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3])));
        if (vs.length === 3) {
          faces.push([vs[0], vs[1], vs[2]]);
          vs.length = 0;
        }
      }
    } else {
      const nTri = buf.byteLength >= 84 ? view.getUint32(80, true) : 0;
      // Reject non-STL data (e.g. a raw STEP/IGES file): a valid binary STL is
      // exactly 84 + nTri*50 bytes. Bail instead of allocating from garbage.
      if (nTri <= 0 || 84 + nTri * 50 > buf.byteLength) {
        console.warn("parseSTL: not a valid binary STL (nTri=" + nTri + ")");
        return { points, faces };
      }
      let off = 84;
      for (let i = 0; i < nTri; i++) {
        off += 12; // skip normal
        const ids = [];
        for (let v = 0; v < 3; v++) {
          ids.push(
            addPt(
              view.getFloat32(off, true),
              view.getFloat32(off + 4, true),
              view.getFloat32(off + 8, true)
            )
          );
          off += 12;
        }
        off += 2; // attribute byte count
        faces.push(ids);
      }
    }
    return { points, faces };
  }

  function hsl(h, s, l) {
    const a = s * Math.min(l, 1 - l);
    const f = (n) => {
      const k = (n + h * 12) % 12;
      return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    };
    return [f(0), f(8), f(4)];
  }

  global.MeshViewer = MeshViewer;
})(window);
