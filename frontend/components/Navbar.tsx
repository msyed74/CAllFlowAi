"use client";

import React from "react";
import Link from "next/link";
import { PhoneCall, ShieldCheck, Activity, Bell } from "lucide-react";

interface NavbarProps {
  isConnected?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ isConnected = true }) => {
  return (
    <header className="h-16 border-b border-border bg-card/60 backdrop-blur-md sticky top-0 z-40 px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold shadow-lg shadow-blue-500/20">
            <PhoneCall className="w-5 h-5" />
          </div>
          <div>
            <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent">
              CALLFLOW AI
            </span>
            <span className="text-[10px] ml-2 px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50 uppercase font-semibold">
              Live Operations
            </span>
          </div>
        </Link>
      </div>

      <div className="flex items-center gap-4">
        {/* Realtime Stream Status */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/80 border border-border text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
            }`}
          />
          <span className="text-slate-300 font-medium">
            {isConnected ? "Live Telephony Stream Active" : "Disconnected"}
          </span>
        </div>

        {/* User Info / Org */}
        <div className="flex items-center gap-2 pl-2 border-l border-border text-sm">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-xs shadow">
            OP
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-semibold text-slate-200">Apex Solutions</p>
            <p className="text-[10px] text-slate-400">Supervisor Console</p>
          </div>
        </div>
      </div>
    </header>
  );
};
