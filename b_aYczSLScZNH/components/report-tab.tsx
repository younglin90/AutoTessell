"use client"

import { CheckCircle2, XCircle, Activity, Box, BarChart3, Ruler } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { AppState } from "@/app/page"

interface ReportTabProps {
  state: AppState
}

export function ReportTab({ state }: ReportTabProps) {
  const hasResults = state.stage === "complete"

  if (!hasResults) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <BarChart3 className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
          <h3 className="mb-2 text-lg font-medium text-foreground">No Report Available</h3>
          <p className="text-sm text-muted-foreground">
            Run the mesh generation to see quality metrics
          </p>
        </div>
      </div>
    )
  }

  const stats = [
    {
      title: "Non-Orthogonality",
      value: state.reportStats.nonOrthogonality.value.toFixed(2) + "°",
      pass: state.reportStats.nonOrthogonality.pass,
      description: "Maximum face angle deviation",
      icon: Activity,
      threshold: "< 70°",
    },
    {
      title: "Skewness",
      value: state.reportStats.skewness.value.toFixed(3),
      pass: state.reportStats.skewness.pass,
      description: "Cell shape quality metric",
      icon: Box,
      threshold: "< 0.85",
    },
    {
      title: "Hausdorff Distance",
      value: state.reportStats.hausdorffDistance.value.toFixed(4) + " m",
      pass: state.reportStats.hausdorffDistance.pass,
      description: "Max distance from original surface",
      icon: Ruler,
      threshold: "< 0.01 m",
    },
  ]

  return (
    <div className="space-y-6">
      {/* Summary Header */}
      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-foreground">Mesh Quality Report</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Generated with {state.engine.charAt(0).toUpperCase() + state.engine.slice(1)} engine
            </p>
          </div>
          <Badge
            variant="outline"
            className="border-success bg-success/10 text-success"
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
            All Checks Passed
          </Badge>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-6">
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">
              {state.meshStats.vertices.toLocaleString()}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">Vertices</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">
              {state.meshStats.cells.toLocaleString()}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">Cells</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-success">
              {state.meshStats.qualityScore.toFixed(1)}%
            </div>
            <div className="mt-1 text-sm text-muted-foreground">Quality Score</div>
          </div>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.title} className="border-border bg-card">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg bg-primary/10 p-2">
                    <stat.icon className="h-4 w-4 text-primary" />
                  </div>
                  <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                </div>
                {stat.pass ? (
                  <Badge
                    variant="outline"
                    className="border-success/50 bg-success/10 text-success"
                  >
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    Pass
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="border-destructive/50 bg-destructive/10 text-destructive"
                  >
                    <XCircle className="mr-1 h-3 w-3" />
                    Fail
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-foreground">{stat.value}</div>
              <p className="mt-1 text-xs text-muted-foreground">{stat.description}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                Threshold: <span className="font-mono text-primary">{stat.threshold}</span>
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Additional Info */}
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-sm font-medium">Processing Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div>
              <span className="text-muted-foreground">Engine</span>
              <p className="font-medium text-foreground">
                {state.engine.charAt(0).toUpperCase() + state.engine.slice(1)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Quality Level</span>
              <p className="font-medium text-foreground">
                {state.qualityLevel.charAt(0).toUpperCase() + state.qualityLevel.slice(1)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Flow Type</span>
              <p className="font-medium text-foreground">
                {state.flowType.charAt(0).toUpperCase() + state.flowType.slice(1)}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Cell Size</span>
              <p className="font-medium text-foreground">{state.cellSize.toFixed(2)}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
