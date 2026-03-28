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
  amount_cents: number;
  stl_filename: string | null;
  target_cells: number;
  mesh_purpose: string;
  mesh_params_json: string | null;
  result_num_cells: number | null;
  result_tier: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DownloadResponse {
  url: string;
  expires_in_seconds: number;
}

export interface MeshParams {
  // pytetwild / dev
  tet_stop_energy?: number;        // 1–50, default 10 (lower = higher quality)
  tet_edge_length_fac?: number;    // 0.02–0.20, override auto from target_cells

  // snappyHexMesh
  snappy_refine_min?: number;      // 0–5
  snappy_refine_max?: number;      // 0–6
  snappy_n_layers?: number;        // 0–12 boundary layers (0 = auto)
  snappy_expansion_ratio?: number; // 1.05–2.0
  snappy_final_layer_thickness?: number; // 0.05–0.9
  snappy_max_non_ortho?: number;   // 50–85

  // Netgen
  netgen_maxh_ratio?: number;      // 5–40 (maxh = L / ratio)

  // MMG post-processing
  mmg_enabled?: boolean;
  mmg_hausd?: number;              // surface fidelity (relative, e.g. 0.01)
  mmg_hgrad?: number;              // 1.0–5.0
}

export async function uploadSTL(
  file: File,
  userId: string,
  targetCells: number = 500_000,
  meshPurpose: "cfd" | "fea" = "cfd",
  meshParams?: MeshParams,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const params = new URLSearchParams({
    user_id: userId,
    target_cells: String(targetCells),
    mesh_purpose: meshPurpose,
  });
  if (meshParams && Object.keys(meshParams).length > 0) {
    params.set("mesh_params", JSON.stringify(meshParams));
  }
  const res = await fetch(`${API_BASE}/upload?${params}`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export interface JobListItem {
  job_id: string;
  status: string;
  stl_filename: string | null;
  target_cells: number;
  mesh_purpose: string;
  has_pro_params: boolean;
  created_at: string;
}

export async function deleteJob(jobId: string, userId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/jobs/${jobId}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Delete failed");
  }
}

export async function listJobs(userId: string): Promise<JobListItem[]> {
  const res = await fetch(
    `${API_BASE}/jobs?user_id=${encodeURIComponent(userId)}`
  );
  if (!res.ok) throw new Error("Failed to fetch job list");
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

export interface PublicConfig {
  mesh_price_cents: number;
  max_stl_size_mb: number;
  max_jobs_per_user: number;
  dev_mode: boolean;
}

export async function getConfig(): Promise<PublicConfig> {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}
