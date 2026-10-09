"use client";

import React, { useEffect, useRef } from "react";
import { User, Bot, Shield, AlertTriangle } from "lucide-react";

export interface TranscriptTurn {
  id?: string;
  speaker_role: "user" | "assistant" | "supervisor" | "system";
  content: string;
  start_time_ms?: number;
  end_time_ms?: number;
  is_interrupted?: boolean;
}

interface LiveTranscriptStreamProps {
  turns: TranscriptTurn[];
  activeCallId?: string | null;
}

export const LiveTranscriptStream: React.FC<LiveTranscriptStreamProps> = ({
  turns,
  activeCallId,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  return (
    <div className="flex flex-col h-full bg-slate-950/60 rounded-xl border border-border overflow-hidden">
      <div className="px-4 py-3 border-b border-border bg-slate-900/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Live Conversation Transcript Stream
          </h3>
        </div>
        {activeCallId && (
          <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
            ID: {activeCallId.slice(0, 8)}...
          </span>
        )}
      </div>

      <div
        ref={scrollRef}
        className="flex-1 p-4 overflow-y-auto space-y-3.5 scroll-smooth max-h-[420px]"
      >
        {turns.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-xs text-center space-y-2">
            <Bot className="w-8 h-8 text-slate-600 animate-bounce" />
            <p>Waiting for live call audio stream...</p>
            <p className="text-[11px] text-slate-600">
              Spoken conversation turns will stream here in real time.
            </p>
          </div>
        ) : (
          turns.map((turn, idx) => {
            const isUser = turn.speaker_role === "user";
            const isAssistant = turn.speaker_role === "assistant";
            const isSupervisor = turn.speaker_role === "supervisor";

            return (
              <div
                key={turn.id || idx}
                className={`flex gap-3 text-sm ${
                  isUser ? "flex-row-reverse" : "flex-row"
                }`}
              >
                {/* Avatar Icon */}
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-white ${
                    isUser
                      ? "bg-amber-600"
                      : isAssistant
                      ? "bg-blue-600"
                      : "bg-purple-600"
                  }`}
                >
                  {isUser ? (
                    <User className="w-4 h-4" />
                  ) : isAssistant ? (
                    <Bot className="w-4 h-4" />
                  ) : (
                    <Shield className="w-4 h-4" />
                  )}
                </div>

                {/* Speech Bubble */}
                <div
                  className={`max-w-[78%] rounded-2xl px-4 py-2.5 shadow-sm leading-relaxed ${
                    isUser
                      ? "bg-amber-950/40 text-amber-100 border border-amber-800/40 rounded-tr-none"
                      : isAssistant
                      ? "bg-slate-900 text-slate-100 border border-slate-800 rounded-tl-none"
                      : "bg-purple-950/50 text-purple-200 border border-purple-800/50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider ${
                        isUser
                          ? "text-amber-400"
                          : isAssistant
                          ? "text-blue-400"
                          : "text-purple-400"
                      }`}
                    >
                      {isUser
                        ? "Prospect"
                        : isAssistant
                        ? "Alex (AI Voice Agent)"
                        : "Supervisor Whisper"}
                    </span>
                    {turn.is_interrupted && (
                      <span className="flex items-center gap-1 text-[10px] text-rose-400 bg-rose-950/60 px-1.5 py-0.2 rounded border border-rose-800/40 font-semibold">
                        <AlertTriangle className="w-3 h-3" /> Interrupted (Barge-in)
                      </span>
                    )}
                  </div>
                  <p className="text-xs leading-normal">{turn.content}</p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
