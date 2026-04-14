"use client"

import { useCallback } from "react"
import { Upload, Play, Settings2, Cpu, Sparkles, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { AppState, MeshEngine, QualityLevel, FlowType } from "@/app/page"

const SERVER_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:9720"

interface SidebarProps {
  state: AppState
  updateState: (updates: Partial<AppState>) => void
  onFileDrop: (file: File) => void
  onRun: () => void
}

export function Sidebar({ state, updateState, onFileDrop, onRun }: SidebarProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer.files[0]
      if (file) {
        const ext = file.name.split(".").pop()?.toLowerCase()
        if (["stl", "step", "stp", "obj"].includes(ext || "")) {
          onFileDrop(file)
        }
      }
    },
    [onFileDrop]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        onFileDrop(file)
      }
    },
    [onFileDrop]
  )

  return (
    <aside className="flex w-[300px] flex-col border-r border-border bg-sidebar p-4">
      {/* Logo */}
      <div className="mb-6 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Cpu className="h-5 w-5 text-primary-foreground" />
        </div>
        <span className="text-lg font-semibold text-foreground">AutoTessell</span>
      </div>

      {/* File Drop Zone */}
      <div
        className="relative mb-6 flex h-32 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/30 transition-colors hover:border-primary hover:bg-muted/50"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <input
          id="file-input"
          type="file"
          accept=".stl,.step,.stp,.obj"
          className="hidden"
          onChange={handleFileSelect}
        />
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        {state.file ? (
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">{state.file.name}</p>
            <p className="text-xs text-muted-foreground">
              {(state.file.size / 1024).toFixed(1)} KB
            </p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm text-muted-foreground">Drop STL/STEP/OBJ file</p>
            <p className="text-xs text-muted-foreground">or click to browse</p>
          </div>
        )}
      </div>

      {/* Engine Selector */}
      <div className="mb-4">
        <Label className="mb-2 block text-sm text-muted-foreground">Mesh Engine</Label>
        <Select
          value={state.engine}
          onValueChange={(value: MeshEngine) => updateState({ engine: value })}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select engine" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Automatic</SelectLabel>
              <SelectItem value="auto">Auto (best tier)</SelectItem>
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Tetrahedral</SelectLabel>
              <SelectItem value="netgen">Netgen</SelectItem>
              <SelectItem value="wildmesh">WildMesh</SelectItem>
              <SelectItem value="tetwild">TetWild</SelectItem>
              <SelectItem value="jigsaw">JIGSAW</SelectItem>
              <SelectItem value="mmg">MMG3D</SelectItem>
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Hex-dominant</SelectLabel>
              <SelectItem value="snappy">SnappyHexMesh</SelectItem>
              <SelectItem value="cfmesh">cfMesh</SelectItem>
              <SelectItem value="cinolib">Cinolib Hex</SelectItem>
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Polyhedral</SelectLabel>
              <SelectItem value="polyDualMesh">PolyDualMesh</SelectItem>
            </SelectGroup>
            <SelectGroup>
              <SelectLabel>Specialty</SelectLabel>
              <SelectItem value="meshpy">MeshPy (2D)</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>

      {/* Quality Level Toggle */}
      <div className="mb-4">
        <Label className="mb-2 block text-sm text-muted-foreground">Quality Level</Label>
        <ToggleGroup
          type="single"
          value={state.qualityLevel}
          onValueChange={(value: QualityLevel) => {
            if (value) updateState({ qualityLevel: value })
          }}
          className="w-full"
          variant="outline"
        >
          <ToggleGroupItem value="draft" className="flex-1 text-xs">
            Draft
          </ToggleGroupItem>
          <ToggleGroupItem value="standard" className="flex-1 text-xs">
            Standard
          </ToggleGroupItem>
          <ToggleGroupItem value="fine" className="flex-1 text-xs">
            Fine
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Advanced Parameters Accordion */}
      <Accordion type="single" collapsible className="mb-6">
        <AccordionItem value="advanced" className="border-b-0">
          <AccordionTrigger className="py-2 text-sm hover:no-underline">
            <div className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              <span>Advanced Parameters</span>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 pt-2">
              {/* Cell Size Slider */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">Cell Size</Label>
                  <span className="text-xs font-mono text-primary">{state.cellSize.toFixed(2)}</span>
                </div>
                <Slider
                  value={[state.cellSize]}
                  onValueChange={([value]) => updateState({ cellSize: value })}
                  min={0.1}
                  max={2.0}
                  step={0.05}
                  className="w-full"
                />
              </div>

              {/* Flow Type */}
              <div>
                <Label className="mb-2 block text-xs text-muted-foreground">Flow Type</Label>
                <ToggleGroup
                  type="single"
                  value={state.flowType}
                  onValueChange={(value: FlowType) => {
                    if (value) updateState({ flowType: value })
                  }}
                  className="w-full"
                  variant="outline"
                  size="sm"
                >
                  <ToggleGroupItem value="internal" className="flex-1 text-xs">
                    Internal
                  </ToggleGroupItem>
                  <ToggleGroupItem value="external" className="flex-1 text-xs">
                    External
                  </ToggleGroupItem>
                </ToggleGroup>
              </div>

              {/* AI Surface Repair */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="ai-repair"
                  checked={state.aiSurfaceRepair}
                  onCheckedChange={(checked) =>
                    updateState({ aiSurfaceRepair: checked === true })
                  }
                />
                <Label
                  htmlFor="ai-repair"
                  className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  AI Surface Repair
                </Label>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Active Tier Badge */}
      {state.activeTier && (
        <div className="mb-2 rounded-md border border-border bg-muted/30 px-3 py-1.5 text-center">
          <span className="text-xs text-muted-foreground">Tier: </span>
          <span className="font-mono text-xs text-primary">{state.activeTier}</span>
        </div>
      )}

      {/* Download Button */}
      {state.stage === "complete" && state.jobId && (
        <Button
          asChild
          variant="outline"
          className="mb-2 h-9 w-full"
          size="sm"
        >
          <a
            href={`${SERVER_URL}/jobs/${state.jobId}/download/polyMesh.zip`}
            download="polyMesh.zip"
          >
            <Download className="mr-2 h-4 w-4" />
            Download polyMesh.zip
          </a>
        </Button>
      )}

      {/* Run Button */}
      <Button
        onClick={onRun}
        disabled={state.isProcessing || !state.file}
        className="h-12 w-full bg-success text-background hover:bg-success/90 disabled:bg-muted disabled:text-muted-foreground"
        size="lg"
      >
        {state.isProcessing ? (
          <>
            <Spinner className="mr-2 h-5 w-5" />
            Processing...
          </>
        ) : (
          <>
            <Play className="mr-2 h-5 w-5" />
            Run Meshing
          </>
        )}
      </Button>
    </aside>
  )
}
