"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listJobs, deleteJob, type JobListItem } from "@/lib/api";
import { loadJobs } from "@/lib/jobs";

const STATUS_COLOR: Record<string, string> = {
  DONE:          "text-green-600",
  FAILED:        "text-red-500",
  REFUND_FAILED: "text-red-500",
  PROCESSING:    "text-blue-600",
  PAID:          "text-blue-500",
  PENDING:       "text-gray-500",
};

const STATUS_LABEL: Record<string, string> = {
  DONE:          "Done",
  FAILED:        "Failed",
  REFUND_FAILED: "Failed",
  PROCESSING:    "Processing…",
  PAID:          "Queued",
  PENDING:       "Pending",
};

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

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleDelete = async (e: React.MouseEvent, jobId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleting(jobId);
    try {
      const userId = getUserId();
      await deleteJob(jobId, userId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } catch {
      // Silently ignore — job might already be gone
    } finally {
      setDeleting(null);
    }
  };

  useEffect(() => {
    const userId = getUserId();

    // Try API first; fall back to localStorage on error
    listJobs(userId)
      .then(setJobs)
      .catch(() => {
        // Map StoredJob → JobListItem shape
        const stored = loadJobs();
        setJobs(stored.map((j) => ({
          job_id: j.jobId,
          status: "UNKNOWN",
          stl_filename: j.filename,
          target_cells: j.targetCells,
          mesh_purpose: j.meshPurpose,
          has_pro_params: j.hasProParams ?? false,
          created_at: j.createdAt,
        })));
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="min-h-screen flex flex-col items-center p-8 bg-gray-50">
      <div className="w-full max-w-2xl flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-gray-800">Recent Jobs</h1>
          <Link href="/mesh/new" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
            + New Job
          </Link>
        </div>

        {loading ? (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-white border rounded-xl p-4 h-16 animate-pulse bg-gray-100" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg mb-2">No jobs yet</p>
            <Link href="/mesh/new" className="text-blue-500 hover:underline text-sm">
              Generate your first mesh
            </Link>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {jobs.map((job) => (
              <Link
                key={job.job_id}
                href={`/mesh/${job.job_id}`}
                className="bg-white border rounded-xl p-4 hover:border-blue-300 transition-colors flex items-center justify-between gap-4"
              >
                <div className="flex flex-col gap-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-800 truncate">
                      {job.stl_filename ?? job.job_id.slice(0, 8)}
                    </span>
                    {job.has_pro_params && (
                      <span className="inline-block px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs font-medium rounded shrink-0">Pro</span>
                    )}
                    <span className={`text-xs font-medium shrink-0 ${STATUS_COLOR[job.status] ?? "text-gray-500"}`}>
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {job.target_cells.toLocaleString()} cells · {job.mesh_purpose.toUpperCase()} · {job.created_at ? new Date(job.created_at).toLocaleString() : ""}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-gray-400 font-mono">{job.job_id.slice(0, 8)}…</span>
                  {["DONE", "FAILED", "REFUND_FAILED"].includes(job.status) && (
                    <button
                      onClick={(e) => handleDelete(e, job.job_id)}
                      disabled={deleting === job.job_id}
                      className="text-gray-300 hover:text-red-400 transition-colors text-xs px-1"
                      title="Delete job"
                    >
                      {deleting === job.job_id ? "…" : "✕"}
                    </button>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
