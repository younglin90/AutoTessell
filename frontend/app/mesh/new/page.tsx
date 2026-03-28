"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { uploadSTL } from "@/lib/api";
import { saveJob } from "@/app/jobs/page";

const CELL_PRESETS = [
  { label: "Coarse", value: 100_000, hint: "~30s · 빠른 확인용" },
  { label: "Standard", value: 500_000, hint: "~3min · 권장", default: true },
  { label: "Fine", value: 2_000_000, hint: "~15min · 고품질" },
  { label: "Custom", value: 0, hint: "직접 입력" },
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

export default function NewMeshPage() {
  const router = useRouter();

  // File
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  // Mesh params
  const [selectedPreset, setSelectedPreset] = useState(500_000);
  const [customCells, setCustomCells] = useState("500000");
  const [meshPurpose, setMeshPurpose] = useState<"cfd" | "fea">("cfd");

  // Submit
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadSTL(file, getUserId(), targetCells, meshPurpose);
      saveJob({
        jobId: res.job_id,
        filename: file.name,
        targetCells,
        meshPurpose,
        createdAt: new Date().toISOString(),
      });
      // dev_mode or post-payment redirect
      router.push(`/mesh/${res.job_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-gray-50">
      <div className="w-full max-w-lg flex flex-col gap-6">
        <h1 className="text-2xl font-semibold text-gray-800">New Mesh Job</h1>

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
              { value: "cfd", label: "CFD", sub: "외부유동 해석 · hex-dominant" },
              { value: "fea", label: "FEA", sub: "구조해석 · tet mesh" },
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
