"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { pollJobStatus, getDownloadUrl, type JobStatus, type MeshParams } from "@/lib/api";

function getUserId(): string {
  if (typeof window === "undefined") return "anon";
  return localStorage.getItem("tessell_user_id") ?? "anon";
}

const STATUS_LABEL: Record<JobStatus["status"], string> = {
  PENDING: "Waiting for payment...",
  PAID: "Queued — starting soon",
  PROCESSING: "Generating mesh...",
  DONE: "Done!",
  FAILED: "Failed",
  REFUND_FAILED: "Failed (refund issue — contact support)",
};

// Human-readable labels for the pro params that differ from defaults
const PARAM_LABELS: Partial<Record<keyof MeshParams, [string, (v: unknown) => string]>> = {
  tet_stop_energy:               ["Stop energy",        (v) => String(v)],
  tet_edge_length_fac:           ["Edge fac",           (v) => String(v)],
  snappy_refine_min:             ["Refine min",         (v) => String(v)],
  snappy_refine_max:             ["Refine max",         (v) => String(v)],
  snappy_n_layers:               ["Boundary layers",    (v) => String(v)],
  snappy_expansion_ratio:        ["Expansion ratio",    (v) => String(v)],
  snappy_final_layer_thickness:  ["Final layer",        (v) => String(v)],
  snappy_max_non_ortho:          ["Max non-ortho",      (v) => `${v}°`],
  netgen_maxh_ratio:             ["Netgen maxh",        (v) => `L/${v}`],
  mmg_enabled:                   ["MMG",                (v) => v ? "on" : "off"],
  mmg_hausd:                     ["MMG hausd",          (v) => String(v)],
  mmg_hgrad:                     ["MMG hgrad",          (v) => String(v)],
};

function ProParamsBadges({ json }: { json: string }) {
  let params: MeshParams;
  try {
    params = JSON.parse(json);
  } catch {
    return null;
  }
  const entries = (Object.entries(params) as [keyof MeshParams, unknown][]).filter(
    ([, v]) => v !== null && v !== undefined
  );
  if (entries.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Pro settings</p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([k, v]) => {
          const def = PARAM_LABELS[k];
          const label = def ? def[0] : String(k);
          const display = def ? def[1](v) : String(v);
          return (
            <span key={k} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs font-mono">
              <span className="text-blue-400">{label}</span>
              {display}
            </span>
          );
        })}
      </div>
    </div>
  );
}

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const userId = getUserId();

    const poll = async () => {
      try {
        const s = await pollJobStatus(jobId, userId);
        setStatus(s);

        if (s.status === "DONE" && !downloadUrl) {
          const d = await getDownloadUrl(jobId, userId);
          setDownloadUrl(d.url);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to fetch status");
      }
    };

    poll();
    const interval = setInterval(() => {
      if (status?.status === "DONE" || status?.status === "FAILED" || status?.status === "REFUND_FAILED") {
        clearInterval(interval);
        return;
      }
      poll();
    }, 4000);

    return () => clearInterval(interval);
  }, [jobId, downloadUrl, status?.status]);

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="text-red-500">{error}</p>
      </main>
    );
  }

  if (!status) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="text-gray-500">Loading...</p>
      </main>
    );
  }

  const isTerminal = ["DONE", "FAILED", "REFUND_FAILED"].includes(status.status);
  const isFailed = status.status === "FAILED" || status.status === "REFUND_FAILED";

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8 bg-gray-50">
      <div className="bg-white rounded-xl shadow-sm border p-8 max-w-md w-full flex flex-col gap-6">
        <h1 className="text-xl font-semibold text-gray-800">Job Status</h1>

        {/* Status indicator */}
        <div className="flex items-center gap-3">
          {!isTerminal && (
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          )}
          <span
            className={`font-medium ${
              status.status === "DONE"
                ? "text-green-600"
                : isFailed
                ? "text-red-500"
                : "text-blue-600"
            }`}
          >
            {STATUS_LABEL[status.status]}
          </span>
        </div>

        {/* Input summary */}
        <div className="bg-gray-50 rounded-lg p-3 text-sm flex flex-wrap gap-x-4 gap-y-1">
          <span className="text-gray-500">
            Target: <span className="font-medium text-gray-700">{status.target_cells.toLocaleString()} cells</span>
          </span>
          <span className="text-gray-500">
            Purpose: <span className="font-medium text-gray-700 uppercase">{status.mesh_purpose}</span>
          </span>
        </div>

        {/* Pro params (if any) */}
        {status.mesh_params_json && (
          <ProParamsBadges json={status.mesh_params_json} />
        )}

        {/* Error */}
        {status.error_message && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
            {status.error_message}
            {status.status === "FAILED" && status.amount_cents > 0 && (
              <p className="mt-1 text-red-500">A full refund has been issued to your card.</p>
            )}
            {status.status === "REFUND_FAILED" && (
              <p className="mt-1 font-medium">Refund could not be processed automatically. Please contact support.</p>
            )}
          </div>
        )}

        {/* Result stats */}
        {status.status === "DONE" && status.result_num_cells && (
          <div className="border border-green-200 bg-green-50 rounded-lg p-4 text-sm flex flex-col gap-1.5">
            <div className="flex justify-between">
              <span className="text-gray-500">Cells generated</span>
              <span className="font-semibold font-mono text-green-800">{status.result_num_cells.toLocaleString()}</span>
            </div>
            {status.result_tier && (
              <div className="flex justify-between">
                <span className="text-gray-500">Engine</span>
                <span className="font-medium font-mono text-gray-700">{status.result_tier}</span>
              </div>
            )}
          </div>
        )}

        {downloadUrl && (
          <a
            href={downloadUrl}
            className="w-full py-3 bg-green-600 text-white rounded-lg font-medium text-center hover:bg-green-700 transition-colors"
          >
            Download mesh.zip
          </a>
        )}

        <p className="text-xs text-gray-400 font-mono break-all">Job ID: {jobId}</p>
      </div>
    </main>
  );
}
