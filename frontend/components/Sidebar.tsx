"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Headphones,
  Users,
  BookOpen,
  Settings,
  BarChart3,
  Sparkles,
} from "lucide-react";

export const Sidebar: React.FC = () => {
  const pathname = usePathname();

  const navItems = [
    {
      label: "Operations Dashboard",
      href: "/",
      icon: Activity,
    },
    {
      label: "Live Supervision Console",
      href: "/supervision",
      icon: Headphones,
      badge: "LIVE",
    },
    {
      label: "Leads & Campaigns",
      href: "/leads",
      icon: Users,
    },
    {
      label: "Knowledge Base (RAG)",
      href: "/knowledge",
      icon: BookOpen,
    },
  ];

  return (
    <aside className="w-64 border-r border-border bg-card/40 backdrop-blur-md flex flex-col shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 space-y-1">
        <p className="px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
          Command Center
        </p>
        <nav className="mt-2 space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? "text-blue-400" : "text-slate-400"}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto p-4 border-t border-border/60">
        <div className="p-3 rounded-lg bg-slate-900/60 border border-border text-xs space-y-2">
          <div className="flex items-center gap-2 text-indigo-400 font-semibold">
            <Sparkles className="w-4 h-4" />
            <span>AI Voice Pipeline</span>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            OpenAI Realtime 24kHz audio bidirectional stream active. Twilio G.711 mu-law transcoding online.
          </p>
        </div>
      </div>
    </aside>
  );
};
