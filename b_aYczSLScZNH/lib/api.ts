/**
 * Auto-Tessell API client
 * Connects to FastAPI backend at localhost:9720
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:9720"
export const WS_BASE = API_BASE.replace(/^http/, "ws")

// ─── Types matching server WebSocket messages ──────────────────────────────

export interface WsProgress {
  type: "progress"
  stage: string
  progress: number
  message: string
}

export interface WsLog {
  type: "log"
  level: "debug" | "info" | "warn" | "error"
  message: string
}

export interface WsStrategy {
  type: "strategy"
  selected_tier: string
  quality_level: string
  cell_size: number
}

export interface WsEvaluation {
  type: "evaluation"
  iteration: number
  verdict: string
  tier: string
  cells: number
  max_non_ortho: number
  max_skewness: number
}

export interface WsResult {
  type: "result"
  success: boolean
  verdict?: string
  cells?: number
  tier?: string
  max_non_ortho?: number
  max_skewness?: number
  output_dir?: string
  message?: string
}

export interface WsError {
  type: "error"
  message: string
}

export type WsMessage = WsProgress | WsLog | WsStrategy | WsEvaluation | WsResult | WsError

// ─── Engine name → backend tier mapping ────────────────────────────────────

export function engineToTier(engine: string): string {
  const map: Record<string, string> = {
    auto: "auto",
    netgen: "netgen",
    wildmesh: "wildmesh",
    tetwild: "tetwild",
    snappy: "snappy",
    cfmesh: "cfmesh",
    cinolib: "tier_cinolib_hex",
    polyDualMesh: "polyDualMesh",
    jigsaw: "tier_jigsaw_fallback",
    mmg: "mmg",
    meshpy: "tier0_2d_meshpy",
  }
  return map[engine] ?? engine
}

// ─── Stage mapping: server stage → frontend ProcessingStage ────────────────

export function serverStageToApp(
  serverStage: string
): "analyzing" | "preprocessing" | "meshing" | "evaluating" | "complete" {
  switch (serverStage) {
    case "init":
    case "analyze":
      return "analyzing"
    case "preprocess":
    case "strategize":
      return "preprocessing"
    case "generate":
      return "meshing"
    case "evaluate":
      return "evaluating"
    case "done":
      return "complete"
    default:
      return "analyzing"
  }
}

// ─── Upload file ────────────────────────────────────────────────────────────

export async function uploadFile(file: File): Promise<string> {
  const form = new FormData()
  form.append("file", file)

  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error ?? `Upload failed: ${res.status}`)
  }
  const data = await res.json()
  return data.job_id as string
}

// ─── WebSocket mesh pipeline ────────────────────────────────────────────────

export interface MeshCallbacks {
  onProgress: (stage: ReturnType<typeof serverStageToApp>, progress: number, message: string) => void
  onLog: (level: WsLog["level"], message: string) => void
  onStrategy: (tier: string) => void
  onEvaluation: (data: WsEvaluation) => void
  onResult: (data: WsResult) => void
  onError: (message: string) => void
}

export function startMeshPipeline(
  jobId: string,
  quality: string,
  engine: string,
  callbacks: MeshCallbacks
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws/mesh/${jobId}`)

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        action: "start",
        quality,
        tier: engineToTier(engine),
      })
    )
  }

  ws.onmessage = (event) => {
    let msg: WsMessage
    try {
      msg = JSON.parse(event.data as string)
    } catch {
      return
    }

    switch (msg.type) {
      case "progress": {
        const appStage = serverStageToApp(msg.stage)
        const pct = Math.round(msg.progress * 100)
        callbacks.onProgress(appStage, pct, msg.message)
        break
      }
      case "log":
        callbacks.onLog(msg.level, msg.message)
        break
      case "strategy":
        callbacks.onStrategy(msg.selected_tier)
        break
      case "evaluation":
        callbacks.onEvaluation(msg)
        break
      case "result":
        callbacks.onResult(msg)
        break
      case "error":
        callbacks.onError(msg.message)
        break
    }
  }

  ws.onerror = () => {
    callbacks.onError("WebSocket connection error")
  }

  return ws
}
