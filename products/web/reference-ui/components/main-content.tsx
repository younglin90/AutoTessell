"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Box, Terminal, FileText } from "lucide-react"
import { ViewerTab } from "@/components/viewer-tab"
import { LogTab } from "@/components/log-tab"
import { ReportTab } from "@/components/report-tab"
import type { AppState } from "@/app/page"

interface MainContentProps {
  state: AppState
}

export function MainContent({ state }: MainContentProps) {
  return (
    <main className="flex flex-1 flex-col overflow-hidden bg-background">
      <Tabs defaultValue="viewer" className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-border px-4 pt-2">
          <TabsList className="bg-muted/50">
            <TabsTrigger value="viewer" className="gap-2">
              <Box className="h-4 w-4" />
              3D Viewer
            </TabsTrigger>
            <TabsTrigger value="log" className="gap-2">
              <Terminal className="h-4 w-4" />
              Log
            </TabsTrigger>
            <TabsTrigger value="report" className="gap-2">
              <FileText className="h-4 w-4" />
              Report
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="viewer" className="flex-1 overflow-hidden m-0">
          <ViewerTab state={state} />
        </TabsContent>

        <TabsContent value="log" className="flex-1 overflow-hidden m-0">
          <LogTab logs={state.logs} />
        </TabsContent>

        <TabsContent value="report" className="flex-1 overflow-auto m-0 p-4">
          <ReportTab state={state} />
        </TabsContent>
      </Tabs>
    </main>
  )
}
