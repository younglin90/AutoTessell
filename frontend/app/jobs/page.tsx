"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface StoredJob {
  jobId: string;
  filename: string;
  targetCells: number;
  meshPurpose: string;
  createdAt: string;
}

const STORAGE_KEY = "tessell_jobs";

export function saveJob(job: StoredJob) {
  if (typeof window === "undefined") return;
  const existing = loadJobs();
  const updated = [job, ...existing.filter((j) => j.jobId !== job.jobId)].slice(0, 20);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

export function loadJobs(): StoredJob[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<StoredJob[]>([]);

  useEffect(() => {
    setJobs(loadJobs());
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

        {jobs.length === 0 ? (
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
                key={job.jobId}
                href={`/mesh/${job.jobId}`}
                className="bg-white border rounded-xl p-4 hover:border-blue-300 transition-colors flex items-center justify-between gap-4"
              >
                <div className="flex flex-col gap-1 min-w-0">
                  <span className="font-medium text-gray-800 truncate">{job.filename}</span>
                  <span className="text-xs text-gray-400">
                    {job.targetCells.toLocaleString()} cells · {job.meshPurpose.toUpperCase()} · {new Date(job.createdAt).toLocaleString()}
                  </span>
                </div>
                <span className="text-xs text-gray-400 font-mono shrink-0">{job.jobId.slice(0, 8)}…</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
