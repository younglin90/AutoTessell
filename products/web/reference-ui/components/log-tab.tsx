"use client"

import { useRef, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { LogEntry } from "@/app/page"

interface LogTabProps {
  logs: LogEntry[]
}

const levelColors = {
  INFO: "text-foreground",
  WARNING: "text-warning",
  ERROR: "text-destructive",
}

const levelBadgeColors = {
  INFO: "bg-muted text-muted-foreground",
  WARNING: "bg-warning/20 text-warning",
  ERROR: "bg-destructive/20 text-destructive",
}

export function LogTab({ logs }: LogTabProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div className="flex h-full flex-col bg-[#0d0d16]">
      {/* Terminal header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-destructive/60" />
          <div className="h-3 w-3 rounded-full bg-warning/60" />
          <div className="h-3 w-3 rounded-full bg-success/60" />
        </div>
        <span className="font-mono text-xs text-muted-foreground">autotessell — bash</span>
      </div>

      {/* Log content */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="p-4 font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-muted-foreground">
              <span className="text-primary">$</span> awaiting commands...
            </div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, index) => (
                <div key={index} className="flex items-start gap-3">
                  <span className="shrink-0 text-xs text-muted-foreground">
                    [{log.timestamp}]
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${
                      levelBadgeColors[log.level]
                    }`}
                  >
                    {log.level}
                  </span>
                  <span className={levelColors[log.level]}>{log.message}</span>
                </div>
              ))}
              <div className="mt-2 flex items-center text-muted-foreground">
                <span className="text-primary">$</span>
                <span className="ml-2 h-4 w-2 animate-pulse bg-primary" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
