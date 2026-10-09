"use client";

import React, { useEffect, useState } from "react";
import {
  PhoneCall,
  Activity,
  CheckCircle2,
  TrendingUp,
  Clock,
  User,
  Headphones,
  ShieldAlert,
  Search,
  ExternalLink,
} from "lucide-react";
import { analyticsApi, callsApi } from "@/lib/api";
import { LiveDashboardSocket, DashboardEvent } from "@/lib/ws";
import { LiveTranscriptStream, TranscriptTurn } from "@/components/LiveTranscriptStream";
import { CallDetailModal } from "@/components/CallDetailModal";

export default function DashboardPage() {
  const [stats, setStats] = useState<any>({
    total_calls: 0,
    active_calls: 0,
    avg_duration_seconds: 0,
    qualification_rate_percent: 0,
    avg_lead_score: 0,
    total_appointments_booked: 0,
  });

  const [calls, setCalls] = useState<any[]>([]);
  const [activeCallId, setActiveCallId] = useState<string | null>(null);
  const [liveTurns, setLiveTurns] = useState<TranscriptTurn[]>([]);
  const [selectedCallDetails, setSelectedCallDetails] = useState<any | null>(null);
  const [searchFilter, setSearchFilter] = useState("");

  // Load KPI stats and recent calls
  const loadData = async () => {
    try {
      const s = await analyticsApi.getStats();
      setStats(s);
    } catch (e) {
      console.error("Failed to load dashboard stats:", e);
    }

    try {
      const c = await callsApi.list();
      setCalls(c.items || []);
      const active = (c.items || []).find((item: any) =>
        ["in_progress", "ringing"].includes(item.status)
      );
      if (active) {
        setActiveCallId(active.id);
      }
    } catch (e) {
      console.error("Failed to load calls:", e);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket Live Stream Connection
  useEffect(() => {
    const orgId = "00000000-0000-0000-0000-000000000000"; // default org stream
    const socket = new LiveDashboardSocket(orgId);
    socket.connect();

    const unsubscribe = socket.subscribe((event: DashboardEvent) => {
      if (event.type === "transcript.turn") {
        setLiveTurns((prev) => [
          ...prev,
          {
            speaker_role: event.speaker_role,
            content: event.content,
            start_time_ms: event.start_time_ms,
            end_time_ms: event.end_time_ms,
          },
        ]);
        if (event.call_id) {
          setActiveCallId(event.call_id);
        }
      } else if (event.type === "call.started") {
        setActiveCallId(event.call_id || null);
        setLiveTurns([]);
        loadData();
      } else if (event.type === "call.ended") {
        loadData();
      }
    });

    return () => {
      unsubscribe();
      socket.disconnect();
    };
  }, []);

  const openCallReview = async (callId: string) => {
    try {
      const details = await callsApi.get(callId);
      setSelectedCallDetails(details);
    } catch (e) {
      console.error("Failed to load call details:", e);
    }
  };

  const filteredCalls = calls.filter((c) =>
    searchFilter ? c.from_number?.includes(searchFilter) || c.to_number?.includes(searchFilter) : true
  );

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100 tracking-tight">
            Live Operations Command Center
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time monitoring of AI voice agents, live PSTN calls, and conversational intelligence.
          </p>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Calls */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-border shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
            <PhoneCall className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Total Calls
            </p>
            <h3 className="text-xl font-bold text-slate-100">{stats.total_calls}</h3>
          </div>
        </div>

        {/* Active Calls */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-border shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
            <Activity className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Active Calls
            </p>
            <h3 className="text-xl font-bold text-emerald-400">{stats.active_calls}</h3>
          </div>
        </div>

        {/* Qualification Rate */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-border shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Qualified Rate
            </p>
            <h3 className="text-xl font-bold text-indigo-300">
              {stats.qualification_rate_percent}%
            </h3>
          </div>
        </div>

        {/* Average Lead Score */}
        <div className="p-4 rounded-xl bg-slate-900/60 border border-border shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              Avg BANT Score
            </p>
            <h3 className="text-xl font-bold text-amber-300">
              {stats.avg_lead_score || "--"} <span className="text-xs text-slate-500">/ 100</span>
            </h3>
          </div>
        </div>
      </div>

      {/* Middle Section: Active Call Card + Real-time Stream */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Call Live Card */}
        <div className="lg:col-span-1 p-5 rounded-xl bg-slate-900/70 border border-border flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-border/80">
              <span className="flex items-center gap-2 text-xs font-bold text-slate-200 uppercase tracking-wider">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
                Active Session
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                G.711 &bull; 24kHz PCM
              </span>
            </div>

            {activeCallId ? (
              <div className="mt-4 space-y-3">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-1">
                  <p className="text-[11px] text-slate-400 font-semibold uppercase">Caller</p>
                  <p className="text-sm font-bold text-slate-100">+1 (555) 019-2831</p>
                  <p className="text-xs text-slate-400">Direction: Inbound Toll-Free</p>
                </div>

                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-1">
                  <p className="text-[11px] text-slate-400 font-semibold uppercase">Voice Persona</p>
                  <p className="text-xs font-medium text-blue-300">Alex (Professional SDR &bull; Alloy)</p>
                </div>
              </div>
            ) : (
              <div className="h-40 flex flex-col items-center justify-center text-slate-500 text-xs text-center space-y-2">
                <Clock className="w-6 h-6 text-slate-600" />
                <p>No phone calls currently in progress.</p>
                <p className="text-[11px] text-slate-600">
                  New inbound or outbound calls will appear here automatically.
                </p>
              </div>
            )}
          </div>

          <div className="space-y-2 pt-4 border-t border-border">
            <a
              href="/supervision"
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow transition"
            >
              <Headphones className="w-4 h-4" /> Open Supervisor Console
            </a>
          </div>
        </div>

        {/* Real-time Streaming Transcript Pane */}
        <div className="lg:col-span-2">
          <LiveTranscriptStream turns={liveTurns} activeCallId={activeCallId} />
        </div>
      </div>

      {/* Bottom Section: Recent Calls History */}
      <div className="p-5 rounded-xl bg-slate-900/60 border border-border space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-400" /> Call History & Extracted Intelligence
          </h3>
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search by phone number..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] tracking-wider border-b border-border">
              <tr>
                <th className="py-2.5 px-3">Call ID</th>
                <th className="py-2.5 px-3">Direction</th>
                <th className="py-2.5 px-3">From / To</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredCalls.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    No calls recorded yet.
                  </td>
                </tr>
              ) : (
                filteredCalls.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-800/30 transition">
                    <td className="py-3 px-3 font-mono text-[11px] text-slate-400">
                      {c.id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-3 capitalize">{c.direction}</td>
                    <td className="py-3 px-3">
                      {c.from_number} &rarr; {c.to_number}
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                          c.status === "completed"
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                            : c.status === "in_progress"
                            ? "bg-blue-950 text-blue-400 border border-blue-800 animate-pulse"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="py-3 px-3">{c.duration_seconds || 0}s</td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => openCallReview(c.id)}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-blue-400 text-xs font-medium transition inline-flex items-center gap-1"
                      >
                        <span>Review</span>
                        <ExternalLink className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal for Call Details */}
      <CallDetailModal
        call={selectedCallDetails}
        onClose={() => setSelectedCallDetails(null)}
      />
    </div>
  );
}
