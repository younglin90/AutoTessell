/**
 * localStorage-based job history for the current browser session.
 * Jobs are keyed by jobId and capped at 20 entries.
 */

const STORAGE_KEY = "tessell_jobs";
const MAX_ENTRIES = 20;

export interface StoredJob {
  jobId: string;
  filename: string;
  targetCells: number;
  meshPurpose: string;
  createdAt: string;
}

export function saveJob(job: StoredJob): void {
  if (typeof window === "undefined") return;
  const existing = loadJobs();
  const updated = [job, ...existing.filter((j) => j.jobId !== job.jobId)].slice(0, MAX_ENTRIES);
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
