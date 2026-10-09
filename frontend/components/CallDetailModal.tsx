"use client";

import React from "react";
import {
  X,
  Calendar,
  Clock,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  FileText,
  User,
  ShieldCheck,
} from "lucide-react";

interface CallDetailModalProps {
  call: any | null;
  onClose: () => void;
}

export const CallDetailModal: React.FC<CallDetailModalProps> = ({ call, onClose }) => {
  if (!call) return null;

  const summary = call.summary;
  const leadScore = call.lead_score;
  const lead = call.lead;
  const transcripts = call.transcripts || [];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-slate-100">
                Call Intelligence Review
              </h2>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
                  call.status === "completed"
                    ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                    : "bg-blue-950/80 text-blue-400 border border-blue-800"
                }`}
              >
                {call.status}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Call ID: <span className="font-mono">{call.id}</span> • From:{" "}
              {call.from_number} • To: {call.to_number}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Top Row: Lead Info & BANT Score Card */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Lead Card */}
            <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                Prospect
              </span>
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-blue-400" />
                <span className="text-sm font-semibold text-slate-200">
                  {lead ? `${lead.first_name || ""} ${lead.last_name || ""}` : "Direct Inbound Caller"}
                </span>
              </div>
              <p className="text-xs text-slate-400">{lead?.phone_number || call.from_number}</p>
              {lead?.status && (
                <div className="pt-1">
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-900/40 text-blue-300 border border-blue-700/40 uppercase">
                    Status: {lead.status}
                  </span>
                </div>
              )}
            </div>

            {/* BANT Composite Score Gauge */}
            <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 flex flex-col justify-between">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                BANT Lead Score
              </span>
              <div className="flex items-baseline gap-2 my-1">
                <span className="text-3xl font-extrabold text-blue-400">
                  {leadScore ? leadScore.composite_score : "--"}
                </span>
                <span className="text-xs text-slate-500 font-semibold">/ 100</span>
              </div>
              <div className="grid grid-cols-4 gap-1 text-center text-[10px] text-slate-400">
                <div className="bg-slate-900/80 p-1 rounded">
                  <p className="font-bold text-slate-300">B: {leadScore?.budget_score ?? "-"}</p>
                </div>
                <div className="bg-slate-900/80 p-1 rounded">
                  <p className="font-bold text-slate-300">A: {leadScore?.authority_score ?? "-"}</p>
                </div>
                <div className="bg-slate-900/80 p-1 rounded">
                  <p className="font-bold text-slate-300">N: {leadScore?.need_score ?? "-"}</p>
                </div>
                <div className="bg-slate-900/80 p-1 rounded">
                  <p className="font-bold text-slate-300">T: {leadScore?.timeline_score ?? "-"}</p>
                </div>
              </div>
            </div>

            {/* Sentiment & Duration Card */}
            <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                Metrics
              </span>
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <Clock className="w-4 h-4 text-indigo-400" />
                <span>Duration: {call.duration_seconds || 0} seconds</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span>
                  Sentiment:{" "}
                  <strong className="text-emerald-300 capitalize">
                    {summary?.sentiment_overall || "Neutral"}
                  </strong>
                </span>
              </div>
            </div>
          </div>

          {/* Executive Summary */}
          {summary && (
            <div className="p-5 rounded-xl bg-slate-950/50 border border-slate-800 space-y-2">
              <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-400" /> Executive AI Summary
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                {summary.executive_summary}
              </p>
              {summary.recommended_follow_up && (
                <div className="mt-3 p-3 rounded-lg bg-blue-950/30 border border-blue-900/40 text-xs text-blue-200">
                  <span className="font-semibold text-blue-300">Recommended Follow-up: </span>
                  {summary.recommended_follow_up}
                </div>
              )}
            </div>
          )}

          {/* Pain Points & Objections */}
          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2">
                <h4 className="text-xs font-bold text-rose-400 uppercase tracking-wider flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" /> Pain Points & Bottlenecks
                </h4>
                <ul className="text-xs text-slate-300 space-y-1.5 list-disc list-inside">
                  {summary.pain_points && summary.pain_points.length > 0 ? (
                    summary.pain_points.map((p: string, idx: number) => (
                      <li key={idx}>{p}</li>
                    ))
                  ) : (
                    <li className="text-slate-500">None explicitly stated.</li>
                  )}
                </ul>
              </div>

              <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2">
                <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" /> Objections Raised
                </h4>
                <ul className="text-xs text-slate-300 space-y-1.5 list-disc list-inside">
                  {summary.objections_raised && summary.objections_raised.length > 0 ? (
                    summary.objections_raised.map((o: string, idx: number) => (
                      <li key={idx}>{o}</li>
                    ))
                  ) : (
                    <li className="text-slate-500">No major objections raised.</li>
                  )}
                </ul>
              </div>
            </div>
          )}

          {/* Transcripts History */}
          <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-3">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              Complete Conversation Dialogue ({transcripts.length} turns)
            </h3>
            <div className="space-y-2 max-h-60 overflow-y-auto pr-2">
              {transcripts.map((t: any, idx: number) => (
                <div
                  key={t.id || idx}
                  className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs space-y-1"
                >
                  <span
                    className={`font-bold text-[10px] uppercase ${
                      t.speaker_role === "user"
                        ? "text-amber-400"
                        : t.speaker_role === "assistant"
                        ? "text-blue-400"
                        : "text-purple-400"
                    }`}
                  >
                    {t.speaker_role === "user" ? "Lead" : "AI Voice Agent"}
                  </span>
                  <p className="text-slate-300">{t.content}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/80 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
