"use client"

import { Progress } from "@/components/ui/progress"
import { CheckCircle2, Circle, Loader2 } from "lucide-react"
import type { ProcessingStage } from "@/app/page"

interface StatusBarProps {
  stage: ProcessingStage
  progress: number
}

const stages: { key: ProcessingStage; label: string }[] = [
  { key: "analyzing", label: "Analyzing" },
  { key: "preprocessing", label: "Preprocessing" },
  { key: "meshing", label: "Meshing" },
  { key: "evaluating", label: "Evaluating" },
]

export function StatusBar({ stage, progress }: StatusBarProps) {
  const getCurrentStageIndex = () => {
    return stages.findIndex((s) => s.key === stage)
  }

  const getStageStatus = (stageKey: ProcessingStage) => {
    const currentIndex = getCurrentStageIndex()
    const stageIndex = stages.findIndex((s) => s.key === stageKey)

    if (stage === "complete") return "complete"
    if (stage === "idle") return "idle"
    if (stageIndex < currentIndex) return "complete"
    if (stageIndex === currentIndex) return "active"
    return "pending"
  }

  return (
    <footer className="flex h-12 items-center gap-4 border-t border-border bg-sidebar px-4">
      {/* Progress Bar */}
      <div className="flex w-48 items-center gap-3">
        <Progress
          value={progress}
          className="h-2 flex-1 bg-muted"
        />
        <span className="w-10 text-right font-mono text-xs text-muted-foreground">
          {progress}%
        </span>
      </div>

      {/* Stage Indicators */}
      <div className="flex items-center gap-1">
        {stages.map((s, index) => {
          const status = getStageStatus(s.key)
          return (
            <div key={s.key} className="flex items-center">
              <div className="flex items-center gap-1.5 px-2">
                {status === "complete" ? (
                  <CheckCircle2 className="h-4 w-4 text-success" />
                ) : status === "active" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground" />
                )}
                <span
                  className={`text-xs font-medium ${
                    status === "active"
                      ? "text-primary"
                      : status === "complete"
                      ? "text-success"
                      : "text-muted-foreground"
                  }`}
                >
                  {s.label}
                </span>
              </div>
              {index < stages.length - 1 && (
                <div
                  className={`h-px w-6 ${
                    getStageStatus(stages[index + 1].key) !== "pending"
                      ? "bg-success"
                      : "bg-muted"
                  }`}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Status Text */}
      <div className="ml-auto">
        <span className="text-xs text-muted-foreground">
          {stage === "idle"
            ? "Ready"
            : stage === "complete"
            ? "Mesh generation complete"
            : `Processing: ${stage.charAt(0).toUpperCase() + stage.slice(1)}...`}
        </span>
      </div>
    </footer>
  )
}
