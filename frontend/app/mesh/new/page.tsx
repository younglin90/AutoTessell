"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import { uploadSTL, type MeshParams } from "@/lib/api";
import { saveJob } from "@/lib/jobs";

const STRIPE_PK = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "";
const stripePromise = STRIPE_PK ? loadStripe(STRIPE_PK) : null;

const CELL_PRESETS = [
  { label: "Coarse", value: 100_000, hint: "~30s · fast check" },
  { label: "Standard", value: 500_000, hint: "~3min · recommended", default: true },
  { label: "Fine", value: 2_000_000, hint: "~15min · high quality" },
  { label: "Custom", value: 0, hint: "manual input" },
] as const;

function getUserId(): string {
  if (typeof window === "undefined") return "anon";
  const key = "tessell_user_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

// Reusable slider row
function ParamRow({
  label,
  hint,
  value,
  min,
  max,
  step,
  onChange,
  format = (v: number) => String(v),
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between items-baseline">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <span className="text-sm font-mono text-blue-700 w-16 text-right">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-blue-500"
      />
      <p className="text-xs text-gray-400">{hint}</p>
    </div>
  );
}

function ToggleRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-gray-700">{label}</p>
        <p className="text-xs text-gray-400">{hint}</p>
      </div>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative inline-flex w-10 h-5 rounded-full transition-colors shrink-0 ${
          value ? "bg-blue-500" : "bg-gray-300"
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
            value ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

const DEFAULT_PRO: Required<MeshParams> = {
  tet_stop_energy: 10,
  tet_edge_length_fac: 0,          // 0 = auto (not sent)
  snappy_refine_min: 0,            // 0 = auto
  snappy_refine_max: 0,            // 0 = auto
  snappy_n_layers: 0,              // 0 = auto
  snappy_expansion_ratio: 1.2,
  snappy_final_layer_thickness: 0.3,
  snappy_max_non_ortho: 70,
  netgen_maxh_ratio: 15,
  mmg_enabled: true,
  mmg_hausd: 0,                    // 0 = auto
  mmg_hgrad: 1.3,
};

// ---------------------------------------------------------------------------
// Stripe payment step (rendered inside <Elements> provider)
// ---------------------------------------------------------------------------

function PaymentStep({
  jobId,
  amountCents,
  onSuccess,
  onError,
}: {
  jobId: string;
  amountCents: number;
  onSuccess: () => void;
  onError: (msg: string) => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [submitting, setSubmitting] = useState(false);

  const handlePay = async () => {
    if (!stripe || !elements) return;
    setSubmitting(true);
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        // Return URL is used by Stripe for redirect-based methods (card doesn't redirect)
        return_url: window.location.origin + `/mesh/${jobId}`,
      },
      redirect: "if_required",
    });
    setSubmitting(false);
    if (error) {
      onError(error.message ?? "Payment failed");
    } else {
      onSuccess();
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="bg-white border rounded-xl p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">Mesh generation</span>
          <span className="font-semibold text-gray-900">
            ${(amountCents / 100).toFixed(2)}
          </span>
        </div>
        <PaymentElement />
      </div>

      <button
        onClick={handlePay}
        disabled={!stripe || submitting}
        className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors"
      >
        {submitting ? "Processing..." : `Pay $${(amountCents / 100).toFixed(2)}`}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Phase = "form" | "payment";

export default function NewMeshPage() {
  const router = useRouter();

  // File
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  // Standard params
  const [selectedPreset, setSelectedPreset] = useState(500_000);
  const [customCells, setCustomCells] = useState("500000");
  const [meshPurpose, setMeshPurpose] = useState<"cfd" | "fea">("cfd");

  // Pro mode
  const [proMode, setProMode] = useState(false);
  const [pro, setPro] = useState<Required<MeshParams>>(DEFAULT_PRO);
  const [proOpen, setProOpen] = useState<Record<string, boolean>>({});

  // Submit / payment phase
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("form");
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [amountCents, setAmountCents] = useState(0);

  const handleFile = useCallback((f: File) => {
    if (!f.name.toLowerCase().endsWith(".stl")) {
      setError("Only .stl files are accepted.");
      return;
    }
    if (f.size > 100 * 1024 * 1024) {
      setError("File must be under 100 MB.");
      return;
    }
    setError(null);
    setFile(f);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const targetCells =
    selectedPreset === 0
      ? Math.max(10_000, Math.min(5_000_000, parseInt(customCells) || 500_000))
      : selectedPreset;

  function setP<K extends keyof MeshParams>(key: K, val: MeshParams[K]) {
    setPro((prev) => ({ ...prev, [key]: val }));
  }

  function toggleSection(key: string) {
    setProOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function buildMeshParams(): MeshParams | undefined {
    if (!proMode) return undefined;
    const p: MeshParams = {};
    if (pro.tet_stop_energy !== 10) p.tet_stop_energy = pro.tet_stop_energy;
    if (pro.tet_edge_length_fac > 0) p.tet_edge_length_fac = pro.tet_edge_length_fac;
    if (pro.snappy_refine_min > 0) p.snappy_refine_min = pro.snappy_refine_min;
    if (pro.snappy_refine_max > 0) p.snappy_refine_max = pro.snappy_refine_max;
    if (pro.snappy_n_layers > 0) p.snappy_n_layers = pro.snappy_n_layers;
    if (pro.snappy_expansion_ratio !== 1.2) p.snappy_expansion_ratio = pro.snappy_expansion_ratio;
    if (pro.snappy_final_layer_thickness !== 0.3) p.snappy_final_layer_thickness = pro.snappy_final_layer_thickness;
    if (pro.snappy_max_non_ortho !== 70) p.snappy_max_non_ortho = pro.snappy_max_non_ortho;
    if (pro.netgen_maxh_ratio !== 15) p.netgen_maxh_ratio = pro.netgen_maxh_ratio;
    if (!pro.mmg_enabled) p.mmg_enabled = false;
    if (pro.mmg_hausd > 0) p.mmg_hausd = pro.mmg_hausd;
    if (pro.mmg_hgrad !== 1.3) p.mmg_hgrad = pro.mmg_hgrad;
    return Object.keys(p).length > 0 ? p : undefined;
  }

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadSTL(file, getUserId(), targetCells, meshPurpose, buildMeshParams());
      saveJob({
        jobId: res.job_id,
        filename: file.name,
        targetCells,
        meshPurpose,
        createdAt: new Date().toISOString(),
        hasProParams: proMode && Object.keys(buildMeshParams() ?? {}).length > 0,
      });

      if (res.client_secret === "dev_mode" || !res.client_secret || !stripePromise) {
        // Dev mode or no Stripe key — go straight to job page
        router.push(`/mesh/${res.job_id}`);
      } else {
        // Production: show payment form
        setPendingJobId(res.job_id);
        setClientSecret(res.client_secret);
        setAmountCents(res.amount_cents);
        setPhase("payment");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Payment phase
  // ---------------------------------------------------------------------------

  if (phase === "payment" && pendingJobId && clientSecret && stripePromise) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-gray-50">
        <div className="w-full max-w-lg flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-semibold text-gray-800">Payment</h1>
            <button
              onClick={() => { setPhase("form"); setError(null); }}
              className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              ← Back
            </button>
          </div>

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <Elements
            stripe={stripePromise}
            options={{ clientSecret, appearance: { theme: "stripe" } }}
          >
            <PaymentStep
              jobId={pendingJobId}
              amountCents={amountCents}
              onSuccess={() => router.push(`/mesh/${pendingJobId}`)}
              onError={(msg) => setError(msg)}
            />
          </Elements>
        </div>
      </main>
    );
  }

  // ---------------------------------------------------------------------------
  // Upload form phase
  // ---------------------------------------------------------------------------

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-gray-50">
      <div className="w-full max-w-lg flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-gray-800">New Mesh Job</h1>
          <Link href="/jobs" className="text-sm text-gray-400 hover:text-gray-600 transition-colors">
            ← Jobs
          </Link>
        </div>

        {/* STL upload */}
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-gray-600 uppercase tracking-wide">1. Upload STL</h2>
          <div
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
              dragging ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-gray-400"
            }`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById("stl-input")?.click()}
          >
            {file ? (
              <p className="text-gray-700 font-medium">
                {file.name} <span className="text-gray-400 font-normal">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
              </p>
            ) : (
              <p className="text-gray-400">Drop an STL file here, or click to browse</p>
            )}
            <input id="stl-input" type="file" accept=".stl" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
          </div>
        </section>

        {/* Cell count */}
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-gray-600 uppercase tracking-wide">2. Target Cell Count</h2>
          <div className="grid grid-cols-4 gap-2">
            {CELL_PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setSelectedPreset(p.value)}
                className={`flex flex-col items-center py-3 px-2 rounded-lg border text-sm transition-colors ${
                  selectedPreset === p.value
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
                }`}
              >
                <span className="font-semibold">{p.label}</span>
                <span className="text-xs text-gray-400 mt-0.5 text-center">{p.hint}</span>
              </button>
            ))}
          </div>

          {selectedPreset === 0 && (
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={10000}
                max={5000000}
                step={10000}
                value={customCells}
                onChange={(e) => setCustomCells(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder="e.g. 1000000"
              />
              <span className="text-sm text-gray-400">cells (10k – 5M)</span>
            </div>
          )}

          {selectedPreset !== 0 && (
            <p className="text-xs text-gray-400">
              {selectedPreset.toLocaleString()} cells
            </p>
          )}
        </section>

        {/* Mesh purpose */}
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-gray-600 uppercase tracking-wide">3. Mesh Purpose</h2>
          <div className="grid grid-cols-2 gap-3">
            {([
              { value: "cfd", label: "CFD", sub: "External flow · hex-dominant" },
              { value: "fea", label: "FEA", sub: "Structural · tet mesh" },
            ] as const).map((opt) => (
              <button
                key={opt.value}
                onClick={() => setMeshPurpose(opt.value)}
                className={`flex flex-col items-start p-4 rounded-xl border text-sm transition-colors ${
                  meshPurpose === opt.value
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <span className={`font-semibold ${meshPurpose === opt.value ? "text-blue-700" : "text-gray-700"}`}>
                  {opt.label}
                </span>
                <span className="text-xs text-gray-400 mt-0.5">{opt.sub}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Pro mode toggle */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-gray-600 uppercase tracking-wide">4. Pro Settings</h2>
              <p className="text-xs text-gray-400 mt-0.5">Fine-tune the mesh engine parameters</p>
            </div>
            <button
              type="button"
              onClick={() => setProMode((v) => !v)}
              className={`relative inline-flex w-11 h-6 rounded-full transition-colors ${
                proMode ? "bg-blue-500" : "bg-gray-300"
              }`}
            >
              <span
                className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                  proMode ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          {proMode && (
            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={() => setPro(DEFAULT_PRO)}
                className="self-end text-xs text-gray-400 hover:text-gray-600 underline"
              >
                Reset to defaults
              </button>

              {/* pytetwild */}
              <ProSection
                title="pytetwild (dev / FEA fallback)"
                description="Tetrahedral mesh quality controls"
                open={!!proOpen["tet"]}
                onToggle={() => toggleSection("tet")}
              >
                <ParamRow
                  label="Stop Energy"
                  hint="Quality threshold — lower = better mesh, longer runtime. Default: 10"
                  value={pro.tet_stop_energy}
                  min={1} max={50} step={0.5}
                  onChange={(v) => setP("tet_stop_energy", v)}
                  format={(v) => v.toFixed(1)}
                />
                <ParamRow
                  label="Edge Length Factor"
                  hint="Cell size relative to bbox diagonal. 0 = auto from cell count. 0.02 (fine) – 0.20 (coarse)"
                  value={pro.tet_edge_length_fac}
                  min={0} max={0.2} step={0.01}
                  onChange={(v) => setP("tet_edge_length_fac", v)}
                  format={(v) => v === 0 ? "auto" : v.toFixed(2)}
                />
              </ProSection>

              {/* snappyHexMesh — CFD only */}
              {meshPurpose === "cfd" && (
                <ProSection
                  title="snappyHexMesh (CFD)"
                  description="OpenFOAM hex-dominant mesher"
                  open={!!proOpen["snappy"]}
                  onToggle={() => toggleSection("snappy")}
                >
                  <div className="grid grid-cols-2 gap-4">
                    <ParamRow
                      label="Refine Min"
                      hint="Surface refinement min level (0 = auto)"
                      value={pro.snappy_refine_min}
                      min={0} max={4} step={1}
                      onChange={(v) => setP("snappy_refine_min", v)}
                      format={(v) => v === 0 ? "auto" : String(v)}
                    />
                    <ParamRow
                      label="Refine Max"
                      hint="Surface refinement max level (0 = auto)"
                      value={pro.snappy_refine_max}
                      min={0} max={6} step={1}
                      onChange={(v) => setP("snappy_refine_max", v)}
                      format={(v) => v === 0 ? "auto" : String(v)}
                    />
                  </div>
                  <ParamRow
                    label="Boundary Layers"
                    hint="Prism layers grown from wall surface. 0 = auto (3–5 based on complexity)"
                    value={pro.snappy_n_layers}
                    min={0} max={8} step={1}
                    onChange={(v) => setP("snappy_n_layers", v)}
                    format={(v) => v === 0 ? "auto" : String(v)}
                  />
                  <ParamRow
                    label="Expansion Ratio"
                    hint="Layer-to-layer thickness growth. 1.1 (uniform) – 1.5 (rapid)"
                    value={pro.snappy_expansion_ratio}
                    min={1.1} max={1.5} step={0.05}
                    onChange={(v) => setP("snappy_expansion_ratio", v)}
                    format={(v) => v.toFixed(2)}
                  />
                  <ParamRow
                    label="Final Layer Thickness"
                    hint="Outermost layer thickness relative to neighbouring cell (0.1–0.5)"
                    value={pro.snappy_final_layer_thickness}
                    min={0.1} max={0.5} step={0.05}
                    onChange={(v) => setP("snappy_final_layer_thickness", v)}
                    format={(v) => v.toFixed(2)}
                  />
                  <ParamRow
                    label="Max Non-Orthogonality"
                    hint="Quality gate: cells above this angle are rejected. 60 (strict) – 85 (lenient)"
                    value={pro.snappy_max_non_ortho}
                    min={60} max={85} step={1}
                    onChange={(v) => setP("snappy_max_non_ortho", v)}
                    format={(v) => `${v}°`}
                  />
                </ProSection>
              )}

              {/* Netgen */}
              <ProSection
                title="Netgen (Tier 0.5)"
                description="Pure-Python tet mesher fallback"
                open={!!proOpen["netgen"]}
                onToggle={() => toggleSection("netgen")}
              >
                <ParamRow
                  label="Max Element Size Ratio"
                  hint="maxh = characteristic_length / ratio. Higher = finer mesh. Default: 15"
                  value={pro.netgen_maxh_ratio}
                  min={5} max={40} step={1}
                  onChange={(v) => setP("netgen_maxh_ratio", v)}
                  format={(v) => `L/${v}`}
                />
              </ProSection>

              {/* MMG */}
              <ProSection
                title="MMG Post-processing"
                description="Quality improvement after pytetwild (requires mmg3d in PATH)"
                open={!!proOpen["mmg"]}
                onToggle={() => toggleSection("mmg")}
              >
                <ToggleRow
                  label="Enable MMG"
                  hint="Run mmg3d quality pass after tet generation"
                  value={pro.mmg_enabled}
                  onChange={(v) => setP("mmg_enabled", v)}
                />
                {pro.mmg_enabled && (
                  <>
                    <ParamRow
                      label="Gradation"
                      hint="Size ratio between adjacent cells. 1.0 (uniform) – 3.0 (rapid change)"
                      value={pro.mmg_hgrad}
                      min={1.0} max={3.0} step={0.1}
                      onChange={(v) => setP("mmg_hgrad", v)}
                      format={(v) => v.toFixed(1)}
                    />
                    <ParamRow
                      label="Hausdorff Distance"
                      hint="Surface approximation fidelity. 0 = auto (L/50). Smaller = more faithful"
                      value={pro.mmg_hausd}
                      min={0} max={0.1} step={0.005}
                      onChange={(v) => setP("mmg_hausd", v)}
                      format={(v) => v === 0 ? "auto" : v.toFixed(3)}
                    />
                  </>
                )}
              </ProSection>
            </div>
          )}
        </section>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          disabled={!file || uploading}
          onClick={handleSubmit}
          className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors"
        >
          {uploading
            ? "Uploading..."
            : `Generate Mesh · ${targetCells.toLocaleString()} cells`}
        </button>
      </div>
    </main>
  );
}

function ProSection({
  title,
  description,
  open,
  onToggle,
  children,
}: {
  title: string;
  description: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-gray-200 rounded-xl bg-white overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
      >
        <div>
          <p className="text-sm font-medium text-gray-800">{title}</p>
          <p className="text-xs text-gray-400">{description}</p>
        </div>
        <span className="text-gray-400 text-sm ml-2">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 flex flex-col gap-4 border-t border-gray-100">
          {children}
        </div>
      )}
    </div>
  );
}
