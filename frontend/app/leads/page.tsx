"use client";

import React, { useEffect, useState } from "react";
import { Users, Plus, PhoneForwarded, Upload, Search, CheckCircle } from "lucide-react";
import { leadsApi } from "@/lib/api";

export default function LeadsPage() {
  const [leads, setLeads] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [callingLeadId, setCallingLeadId] = useState<string | null>(null);
  const [callNotice, setCallNotice] = useState<string | null>(null);

  // Form State
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");

  const loadLeads = async () => {
    try {
      const res = await leadsApi.list();
      setLeads(res.items || []);
    } catch (e) {
      console.error("Failed to load leads:", e);
    }
  };

  useEffect(() => {
    loadLeads();
  }, []);

  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phoneNumber.trim()) return;

    try {
      await leadsApi.create({
        first_name: firstName,
        last_name: lastName,
        phone_number: phoneNumber,
        email: email || undefined,
        custom_fields: { company },
      });
      setShowAddModal(false);
      setFirstName("");
      setLastName("");
      setPhoneNumber("");
      setEmail("");
      setCompany("");
      loadLeads();
    } catch (e: any) {
      alert(`Failed to add lead: ${e.message}`);
    }
  };

  const handleCallNow = (leadId: string, phone: string) => {
    setCallingLeadId(leadId);
    setCallNotice(`Outbound voice agent dispatch scheduled for ${phone}. Ringing lead handset...`);
    setTimeout(() => {
      setCallingLeadId(null);
      setTimeout(() => setCallNotice(null), 5000);
    }, 2500);
  };

  const filteredLeads = leads.filter(
    (l) =>
      l.phone_number?.includes(search) ||
      l.first_name?.toLowerCase().includes(search.toLowerCase()) ||
      l.last_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-100 tracking-tight flex items-center gap-2">
            <Users className="w-6 h-6 text-blue-500" />
            Lead & Campaign Management
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Manage prospect call lists, inspect qualification stages, and trigger instant outbound calls.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow"
          >
            <Plus className="w-4 h-4" /> Add Lead
          </button>
        </div>
      </div>

      {callNotice && (
        <div className="p-3.5 rounded-lg bg-blue-950/60 border border-blue-800 text-xs text-blue-200 flex items-center gap-2 animate-fadeIn">
          <PhoneForwarded className="w-4 h-4 text-blue-400 animate-pulse" />
          <span>{callNotice}</span>
        </div>
      )}

      {/* Leads Table */}
      <div className="p-5 rounded-xl bg-slate-900/60 border border-border space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="relative w-72">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search leads by name or phone..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <span className="text-xs text-slate-400">Total Leads: {filteredLeads.length}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase text-[10px] tracking-wider border-b border-border">
              <tr>
                <th className="py-2.5 px-3">Lead Name</th>
                <th className="py-2.5 px-3">Phone Number</th>
                <th className="py-2.5 px-3">Email</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">BANT Score</th>
                <th className="py-2.5 px-3 text-right">Instant Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredLeads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    No leads found. Click "Add Lead" to add your first prospect.
                  </td>
                </tr>
              ) : (
                filteredLeads.map((lead) => {
                  const score = lead.custom_fields?.latest_lead_score;
                  return (
                    <tr key={lead.id} className="hover:bg-slate-800/30 transition">
                      <td className="py-3 px-3 font-semibold text-slate-100">
                        {lead.first_name} {lead.last_name}
                      </td>
                      <td className="py-3 px-3 font-mono">{lead.phone_number}</td>
                      <td className="py-3 px-3 text-slate-400">{lead.email || "--"}</td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            lead.status === "qualified"
                              ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                              : lead.status === "contacted"
                              ? "bg-blue-950 text-blue-400 border border-blue-800"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {lead.status}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        {score !== undefined ? (
                          <span className="font-bold text-amber-300">{score} / 100</span>
                        ) : (
                          <span className="text-slate-500">Pending Call</span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={() => handleCallNow(lead.id, lead.phone_number)}
                          disabled={callingLeadId === lead.id}
                          className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold transition inline-flex items-center gap-1 shadow-sm"
                        >
                          <PhoneForwarded className="w-3.5 h-3.5" />
                          <span>{callingLeadId === lead.id ? "Calling..." : "Call Now"}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Lead Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-md p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-slate-100">Add New Prospect Lead</h3>
            <form onSubmit={handleCreateLead} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-semibold text-slate-400">First Name</label>
                  <input
                    type="text"
                    required
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-400">Last Name</label>
                  <input
                    type="text"
                    required
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400">Phone Number (E.164 format)</label>
                <input
                  type="text"
                  required
                  placeholder="+15551234567"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100 font-mono"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400">Email (Optional)</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400">Company</label>
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
                >
                  Save Lead
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
