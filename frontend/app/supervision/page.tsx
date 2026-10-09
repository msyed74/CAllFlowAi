"use client";

import React, { useEffect, useState } from "react";
import {
  Headphones,
  Send,
  ShieldAlert,
  Mic,
  Volume2,
  Activity,
  AlertTriangle,
  UserCheck,
} from "lucide-react";
import { callsApi } from "@/lib/api";
import { LiveDashboardSocket, DashboardEvent } from "@/lib/ws";
import { LiveTranscriptStream, TranscriptTurn } from "@/components/LiveTranscriptStream";

export default function SupervisionPage() {
  const [activeCalls, setActiveCalls] = useState<any[]>([]);
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [whisperText, setWhisperText] = useState("");
  const [whisperStatus, setWhisperStatus] = useState<string | null>(null);
  const [takeoverStatus, setTakeoverStatus] = useState<string | null>(null);
  const [liveTurns, setLiveTurns] = useState<TranscriptTurn[]>([]);
  const [isListening, setIsListening] = useState(true);

  // Poll for active calls
  const fetchActiveCalls = async () => {
    try {
      const res = await callsApi.list("in_progress");
      setActiveCalls(res.items || []);
      if (!selectedCallId && res.items?.length > 0) {
        setSelectedCallId(res.items[0].id);
      }
    } catch (e) {
      console.error("Failed to load active calls:", e);
    }
  };

  useEffect(() => {
    fetchActiveCalls();
    const interval = setInterval(fetchActiveCalls, 4000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket Live Stream
  useEffect(() => {
    const orgId = "00000000-0000-0000-0000-000000000000";
    const socket = new LiveDashboardSocket(orgId);
    socket.connect();

    const unsubscribe = socket.subscribe((event: DashboardEvent) => {
      if (event.type === "transcript.turn" && event.call_id === selectedCallId) {
        setLiveTurns((prev) => [
          ...prev,
          {
            speaker_role: event.speaker_role,
            content: event.content,
            start_time_ms: event.start_time_ms,
            end_time_ms: event.end_time_ms,
          },
        ]);
      } else if (event.type === "call.ended" && event.call_id === selectedCallId) {
        fetchActiveCalls();
      }
    });

    return () => {
      unsubscribe();
      socket.disconnect();
    };
  }, [selectedCallId]);

  // Supervisor Whisper
  const handleSendWhisper = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCallId || !whisperText.trim()) return;

    try {
      setWhisperStatus("Sending whisper to AI agent...");
      await callsApi.whisper(selectedCallId, whisperText);
      setWhisperStatus("Whisper delivered! Agent is adjusting conversational tactic.");
      setWhisperText("");
      setTimeout(() => setWhisperStatus(null), 4000);
    } catch (e: any) {
      setWhisperStatus(`Failed: ${e.message}`);
    }
  };

  // Supervisor Human Takeover
  const handleTakeover = async () => {
    if (!selectedCallId) return;
    const confirm = window.confirm(
      "Are you sure you want to take over this call? The AI voice agent will bridge the call to your human extension immediately."
    );
    if (!confirm) return;

    try {
      setTakeoverStatus("Initiating warm transfer to human queue...");
      await callsApi.takeover(selectedCallId, "Supervisor intervention requested from operations UI");
      setTakeoverStatus("Call successfully transferred to human agent.");
      setTimeout(() => setTakeoverStatus(null), 5000);
    } catch (e: any) {
      setTakeoverStatus(`Takeover failed: ${e.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 tracking-tight flex items-center gap-2">
          <Headphones className="w-6 h-6 text-blue-500" />
          Supervisor Intervention Console
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Monitor ongoing calls live, inject real-time coaching prompts (whisper), or take over immediately.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Active Call Selector & Controls */}
        <div className="space-y-6">
          {/* Active Calls List */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-border space-y-3">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>Active Calls ({activeCalls.length})</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            </h3>

            {activeCalls.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs">
                No calls currently active for supervision.
              </div>
            ) : (
              <div className="space-y-2">
                {activeCalls.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setSelectedCallId(c.id);
                      setLiveTurns([]);
                    }}
                    className={`w-full text-left p-3 rounded-lg border text-xs transition flex items-center justify-between ${
                      selectedCallId === c.id
                        ? "bg-blue-950/40 border-blue-500/60 text-white shadow-sm"
                        : "bg-slate-950/40 border-slate-800 text-slate-300 hover:bg-slate-800/40"
                    }`}
                  >
                    <div>
                      <p className="font-semibold text-slate-100">
                        {c.from_number} &rarr; {c.to_number}
                      </p>
                      <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                        ID: {c.id.slice(0, 8)}...
                      </p>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 uppercase font-bold">
                      Live
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Audio Monitor Status */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-border space-y-3">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Volume2 className="w-4 h-4 text-indigo-400" /> Audio Stream Monitor
            </h3>
            <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Audio Codec:</span>
                <span className="font-mono text-slate-200">G.711 mu-law (8kHz)</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Model Audio:</span>
                <span className="font-mono text-slate-200">Linear PCM16 (24kHz)</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Stream Status:</span>
                <span className="text-emerald-400 font-bold">Connected &bull; Low Latency</span>
              </div>
            </div>
            <button
              onClick={() => setIsListening(!isListening)}
              className={`w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition ${
                isListening
                  ? "bg-emerald-900/40 border border-emerald-700/60 text-emerald-300"
                  : "bg-slate-800 hover:bg-slate-700 text-slate-300"
              }`}
            >
              <Headphones className="w-4 h-4" />
              {isListening ? "Audio Monitoring Active" : "Mute Monitor Audio"}
            </button>
          </div>

          {/* Emergency Human Takeover Button */}
          <div className="p-4 rounded-xl bg-rose-950/20 border border-rose-900/40 space-y-3">
            <h3 className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4" /> Emergency Takeover
            </h3>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Instantly bridges the phone call away from the AI agent directly into your human hunt group.
            </p>
            {takeoverStatus && (
              <p className="text-xs text-amber-300 font-medium">{takeoverStatus}</p>
            )}
            <button
              onClick={handleTakeover}
              disabled={!selectedCallId}
              className="w-full py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-bold text-xs tracking-wide shadow-lg shadow-rose-600/20 flex items-center justify-center gap-2 transition"
            >
              <UserCheck className="w-4 h-4" /> Take Over Call Now
            </button>
          </div>
        </div>

        {/* Right Columns: Live Transcript & Whisper Box */}
        <div className="lg:col-span-2 space-y-6">
          {/* Transcript Box */}
          <LiveTranscriptStream turns={liveTurns} activeCallId={selectedCallId} />

          {/* Supervisor Whisper Box */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-border space-y-3">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Mic className="w-4 h-4 text-purple-400" /> Supervisor Whisper Mode
            </h3>
            <p className="text-xs text-slate-400">
              Type advice below to inject coaching instructions directly into the AI agent. The caller will <strong>not</strong> hear this message.
            </p>

            <form onSubmit={handleSendWhisper} className="space-y-3">
              <div className="relative">
                <textarea
                  rows={2}
                  placeholder="e.g. Offer them the complimentary onboarding package if they commit this week..."
                  value={whisperText}
                  onChange={(e) => setWhisperText(e.target.value)}
                  disabled={!selectedCallId}
                  className="w-full p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500 resize-none"
                />
              </div>

              {whisperStatus && (
                <p className="text-xs text-purple-300 font-medium">{whisperStatus}</p>
              )}

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={!selectedCallId || !whisperText.trim()}
                  className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold text-xs flex items-center gap-2 transition"
                >
                  <Send className="w-3.5 h-3.5" /> Inject Whisper Prompt
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
