const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface UploadResponse {
  job_id: string;
  client_secret: string;
  amount_cents: number;
}

export interface JobStatus {
  job_id: string;
  status: "PENDING" | "PAID" | "PROCESSING" | "DONE" | "FAILED" | "REFUND_FAILED";
  error_message: string | null;
  download_ready: boolean;
}

export interface DownloadResponse {
  url: string;
  expires_in_seconds: number;
}

export async function uploadSTL(
  file: File,
  userId: string
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/upload?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function pollJobStatus(jobId: string, userId: string): Promise<JobStatus> {
  const res = await fetch(
    `${API_BASE}/jobs/${jobId}?user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) throw new Error("Failed to fetch job status");
  return res.json();
}

export async function getDownloadUrl(jobId: string, userId: string): Promise<DownloadResponse> {
  const res = await fetch(
    `${API_BASE}/jobs/${jobId}/download?user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) throw new Error("Download not ready");
  return res.json();
}
