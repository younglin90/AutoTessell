"use client"

import { useState, useCallback, useRef } from "react"
import { Sidebar } from "@/components/sidebar"
import { MainContent } from "@/components/main-content"
import { StatusBar } from "@/components/status-bar"
import { uploadFile, startMeshPipeline } from "@/lib/api"
import type { WsEvaluation, WsResult } from "@/lib/api"

export type MeshEngine =
  | "auto"
  | "netgen" | "wildmesh" | "tetwild"          // Tetrahedral
  | "snappy" | "cfmesh" | "cinolib"            // Hex-dominant
  | "polyDualMesh"                              // Polyhedral
  | "jigsaw" | "mmg" | "meshpy"               // Fallback / specialty

export type QualityLevel = "draft" | "standard" | "fine"
export type FlowType = "internal" | "external"
export type ProcessingStage =
  | "idle"
  | "analyzing"
  | "preprocessing"
  | "meshing"
  | "evaluating"
  | "complete"

export interface MeshStats {
  vertices: number
  cells: number
  qualityScore: number
}

export interface ReportStats {
  nonOrthogonality: { value: number; pass: boolean }
  skewness: { value: number; pass: boolean }
  hausdorffDistance: { value: number; pass: boolean }
}

export interface LogEntry {
  timestamp: string
  level: "INFO" | "WARNING" | "ERROR"
  message: string
}

export interface AppState {
  file: File | null
  engine: MeshEngine
  qualityLevel: QualityLevel
  cellSize: number
  flowType: FlowType
  aiSurfaceRepair: boolean
  isProcessing: boolean
  stage: ProcessingStage
  progress: number
  meshStats: MeshStats
  reportStats: ReportStats
  logs: LogEntry[]
  activeTier: string
  jobId: string
}

const initialState: AppState = {
  file: null,
  engine: "auto",
  qualityLevel: "standard",
  cellSize: 0.5,
  flowType: "external",
  aiSurfaceRepair: true,
  isProcessing: false,
  stage: "idle",
  progress: 0,
  meshStats: { vertices: 0, cells: 0, qualityScore: 0 },
  reportStats: {
    nonOrthogonality: { value: 0, pass: true },
    skewness: { value: 0, pass: true },
    hausdorffDistance: { value: 0, pass: true },
  },
  logs: [],
  activeTier: "",
  jobId: "",
}

export default function AutoTessellPage() {
  const [state, setState] = useState<AppState>(initialState)
  const wsRef = useRef<WebSocket | null>(null)

  const addLog = useCallback(
    (level: LogEntry["level"], message: string) => {
      const timestamp = new Date().toISOString().split("T")[1].slice(0, 12)
      setState((prev) => ({
        ...prev,
        logs: [...prev.logs, { timestamp, level, message }],
      }))
    },
    []
  )

  const updateState = useCallback((updates: Partial<AppState>) => {
    setState((prev) => ({ ...prev, ...updates }))
  }, [])

  const handleFileDrop = useCallback(
    (file: File) => {
      updateState({ file })
      addLog("INFO", `File loaded: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`)
    },
    [updateState, addLog]
  )

  const runMeshing = useCallback(async () => {
    const { file, engine, qualityLevel } = state
    if (!file) {
      addLog("ERROR", "No file selected. Please upload a geometry file.")
      return
    }

    // Close any existing WebSocket
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    updateState({
      isProcessing: true,
      stage: "analyzing",
      progress: 0,
      logs: [],
      activeTier: "",
      jobId: "",
      meshStats: { vertices: 0, cells: 0, qualityScore: 0 },
      reportStats: {
        nonOrthogonality: { value: 0, pass: true },
        skewness: { value: 0, pass: true },
        hausdorffDistance: { value: 0, pass: true },
      },
    })
    addLog("INFO", `Uploading ${file.name}...`)

    let jobId: string
    try {
      jobId = await uploadFile(file)
      updateState({ jobId })
      addLog("INFO", `Job created: ${jobId}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      addLog("ERROR", `Upload failed: ${msg}`)
      updateState({ isProcessing: false, stage: "idle" })
      return
    }

    addLog("INFO", `Starting mesh generation — engine: ${engine}, quality: ${qualityLevel}`)

    const ws = startMeshPipeline(jobId, qualityLevel, engine, {
      onProgress(appStage, pct, message) {
        updateState({ stage: appStage, progress: pct })
        if (message) addLog("INFO", message)
      },
      onLog(level, message) {
        const logLevel: LogEntry["level"] =
          level === "error" ? "ERROR" : level === "warn" ? "WARNING" : "INFO"
        addLog(logLevel, message)
      },
      onStrategy(tier) {
        updateState({ activeTier: tier })
        addLog("INFO", `Strategy: tier=${tier}`)
      },
      onEvaluation(data: WsEvaluation) {
        const pass = data.verdict === "PASS" || data.verdict === "PASS_WITH_WARNINGS"
        addLog(
          pass ? "INFO" : "WARNING",
          `Evaluation iter ${data.iteration}: ${data.verdict} — ` +
            `cells=${data.cells.toLocaleString()}, ` +
            `non-ortho=${data.max_non_ortho.toFixed(1)}°, ` +
            `skewness=${data.max_skewness.toFixed(3)}`
        )
        // Update KPI live
        updateState({
          reportStats: {
            nonOrthogonality: { value: data.max_non_ortho, pass: data.max_non_ortho < 70 },
            skewness: { value: data.max_skewness, pass: data.max_skewness < 0.85 },
            hausdorffDistance: { value: 0, pass: true }, // backend doesn't stream Hausdorff yet
          },
        })
      },
      onResult(data: WsResult) {
        if (data.success) {
          const cells = data.cells ?? 0
          // qualityScore: heuristic based on non-ortho and skewness
          const nonOrtho = data.max_non_ortho ?? 0
          const skew = data.max_skewness ?? 0
          const score = Math.max(0, 100 - nonOrtho * 0.5 - skew * 20)
          updateState({
            isProcessing: false,
            stage: "complete",
            progress: 100,
            meshStats: {
              vertices: Math.round(cells * 0.6), // estimate
              cells,
              qualityScore: score,
            },
            reportStats: {
              nonOrthogonality: { value: nonOrtho, pass: nonOrtho < 70 },
              skewness: { value: skew, pass: skew < 0.85 },
              hausdorffDistance: { value: 0, pass: true },
            },
          })
          addLog("INFO", `Mesh generation complete: ${cells.toLocaleString()} cells — ${data.verdict}`)
        } else {
          updateState({ isProcessing: false, stage: "idle" })
          addLog("ERROR", `Mesh generation failed: ${data.message ?? "unknown error"}`)
        }
        wsRef.current = null
      },
      onError(message) {
        updateState({ isProcessing: false, stage: "idle" })
        addLog("ERROR", `Error: ${message}`)
        wsRef.current = null
      },
    })

    wsRef.current = ws
  }, [state, updateState, addLog])

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          state={state}
          updateState={updateState}
          onFileDrop={handleFileDrop}
          onRun={runMeshing}
        />
        <MainContent state={state} />
      </div>
      <StatusBar stage={state.stage} progress={state.progress} />
    </div>
  )
}
