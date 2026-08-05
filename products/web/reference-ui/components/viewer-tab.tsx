"use client"

import { useRef, useState, useEffect } from "react"
import { RotateCcw, ZoomIn, ZoomOut, Move } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { AppState } from "@/app/page"

interface ViewerTabProps {
  state: AppState
}

export function ViewerTab({ state }: ViewerTabProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [rotation, setRotation] = useState({ x: 0.5, y: 0.5 })
  const [zoom, setZoom] = useState(1)

  // Simple 3D wireframe mesh preview animation
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let animationId: number
    let time = 0

    const draw = () => {
      const width = canvas.width
      const height = canvas.height
      const centerX = width / 2
      const centerY = height / 2

      // Clear canvas
      ctx.fillStyle = "#12121f"
      ctx.fillRect(0, 0, width, height)

      // Draw grid
      ctx.strokeStyle = "#252542"
      ctx.lineWidth = 1
      const gridSize = 40 * zoom
      for (let x = centerX % gridSize; x < width; x += gridSize) {
        ctx.beginPath()
        ctx.moveTo(x, 0)
        ctx.lineTo(x, height)
        ctx.stroke()
      }
      for (let y = centerY % gridSize; y < height; y += gridSize) {
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
        ctx.stroke()
      }

      if (state.file || state.stage === "complete") {
        // Draw a rotating 3D mesh preview
        const meshSize = 120 * zoom
        const rotX = rotation.x + time * 0.3
        const rotY = rotation.y + time * 0.2

        // Create vertices for a complex mesh-like shape
        const vertices: [number, number, number][] = []
        const edges: [number, number][] = []

        // Generate icosphere-like vertices
        const phi = (1 + Math.sqrt(5)) / 2
        const baseVerts: [number, number, number][] = [
          [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
          [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
          [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
        ]

        // Normalize and add
        baseVerts.forEach(v => {
          const len = Math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
          vertices.push([v[0] / len, v[1] / len, v[2] / len])
        })

        // Add subdivided vertices
        const midpoints = [
          [0, 1], [1, 7], [7, 0], [0, 5], [5, 1],
          [1, 9], [9, 7], [7, 8], [8, 1], [9, 8],
          [5, 9], [4, 5], [11, 4], [11, 5], [0, 11],
          [4, 9], [4, 3], [3, 9], [3, 8], [4, 2],
          [2, 3], [11, 2], [2, 10], [10, 11], [0, 10],
          [6, 2], [3, 6], [6, 8], [7, 6], [10, 6]
        ]

        midpoints.forEach(([a, b]) => {
          edges.push([a, b])
        })

        // Project and draw
        const project = (x: number, y: number, z: number): [number, number] => {
          // Apply rotation
          const cosX = Math.cos(rotX)
          const sinX = Math.sin(rotX)
          const cosY = Math.cos(rotY)
          const sinY = Math.sin(rotY)

          let x1 = x * cosY - z * sinY
          let z1 = x * sinY + z * cosY
          let y1 = y * cosX - z1 * sinX
          let z2 = y * sinX + z1 * cosX

          const scale = meshSize / (2 + z2 * 0.5)
          return [centerX + x1 * scale, centerY + y1 * scale]
        }

        // Draw edges with depth-based coloring
        ctx.lineCap = "round"
        edges.forEach(([a, b]) => {
          const v1 = vertices[a]
          const v2 = vertices[b]
          if (!v1 || !v2) return

          const [x1, y1] = project(v1[0], v1[1], v1[2])
          const [x2, y2] = project(v2[0], v2[1], v2[2])

          const avgZ = (v1[2] + v2[2]) / 2
          const alpha = 0.3 + (avgZ + 1) * 0.35

          ctx.strokeStyle = `rgba(0, 212, 255, ${alpha})`
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.moveTo(x1, y1)
          ctx.lineTo(x2, y2)
          ctx.stroke()
        })

        // Draw vertices
        vertices.forEach(v => {
          const [px, py] = project(v[0], v[1], v[2])
          const alpha = 0.4 + (v[2] + 1) * 0.3
          ctx.fillStyle = `rgba(0, 255, 136, ${alpha})`
          ctx.beginPath()
          ctx.arc(px, py, 2, 0, Math.PI * 2)
          ctx.fill()
        })
      } else {
        // No file loaded message
        ctx.fillStyle = "#9090a8"
        ctx.font = "14px monospace"
        ctx.textAlign = "center"
        ctx.fillText("Drop a geometry file to preview", centerX, centerY)
      }

      time += 0.01
      animationId = requestAnimationFrame(draw)
    }

    const handleResize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio
      canvas.height = canvas.offsetHeight * window.devicePixelRatio
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio)
    }

    handleResize()
    window.addEventListener("resize", handleResize)
    draw()

    return () => {
      window.removeEventListener("resize", handleResize)
      cancelAnimationFrame(animationId)
    }
  }, [state.file, state.stage, rotation, zoom])

  return (
    <div className="relative h-full w-full">
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        style={{ imageRendering: "auto" }}
      />

      {/* Floating Stats Overlay */}
      {state.stage === "complete" && (
        <div className="absolute left-4 top-4 rounded-lg border border-border bg-card/90 p-4 backdrop-blur-sm">
          <h3 className="mb-3 text-sm font-semibold text-foreground">Mesh Statistics</h3>
          <div className="space-y-2 font-mono text-xs">
            <div className="flex items-center justify-between gap-6">
              <span className="text-muted-foreground">Vertices</span>
              <span className="text-primary">{state.meshStats.vertices.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between gap-6">
              <span className="text-muted-foreground">Cells</span>
              <span className="text-primary">{state.meshStats.cells.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between gap-6">
              <span className="text-muted-foreground">Quality</span>
              <span className="text-success">{state.meshStats.qualityScore.toFixed(1)}%</span>
            </div>
          </div>
        </div>
      )}

      {/* View Controls */}
      <div className="absolute bottom-4 right-4 flex gap-2">
        <Button
          variant="secondary"
          size="icon"
          onClick={() => setRotation({ x: 0.5, y: 0.5 })}
          className="h-9 w-9"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          onClick={() => setZoom(z => Math.min(2, z + 0.2))}
          className="h-9 w-9"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          onClick={() => setZoom(z => Math.max(0.5, z - 0.2))}
          className="h-9 w-9"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          onClick={() => setRotation(r => ({ x: r.x + 0.5, y: r.y + 0.3 }))}
          className="h-9 w-9"
        >
          <Move className="h-4 w-4" />
        </Button>
      </div>

      {/* Processing Indicator */}
      {state.isProcessing && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            <span className="text-sm font-medium text-foreground">
              {state.stage.charAt(0).toUpperCase() + state.stage.slice(1)}...
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
