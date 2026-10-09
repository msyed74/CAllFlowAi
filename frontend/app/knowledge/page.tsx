"use client";

import React, { useEffect, useState } from "react";
import { BookOpen, Upload, FileText, CheckCircle, Search, Sparkles } from "lucide-react";
import { knowledgeApi } from "@/lib/api";

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [sourceType, setSourceType] = useState("faq_manual");
  const [ingesting, setIngesting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadDocs = async () => {
    try {
      const res = await knowledgeApi.listDocuments();
      setDocuments(res.items || []);
    } catch (e) {
      console.error("Failed to load documents:", e);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;

    try {
      setIngesting(true);
      setStatusMessage("Chunking tokens (500-token window) and generating OpenAI embeddings...");
      const res = await knowledgeApi.ingest(title, content, sourceType);
      setStatusMessage(`Success! Ingested ${res.chunks_ingested} vector chunks into Qdrant.`);
      setTitle("");
      setContent("");
      loadDocs();
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (e: any) {
      setStatusMessage(`Ingestion error: ${e.message}`);
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-100 tracking-tight flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-blue-500" />
          Knowledge Base (RAG Retrieval Engine)
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Upload product documentation, pricing tables, and FAQs. The AI voice agent searches these chunks live in &lt;180ms.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload Form */}
        <div className="lg:col-span-1 p-5 rounded-xl bg-slate-900/60 border border-border space-y-4">
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <Upload className="w-4 h-4 text-blue-400" /> Ingest Knowledge Document
          </h3>

          <form onSubmit={handleIngest} className="space-y-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-400">Document Title</label>
              <input
                type="text"
                required
                placeholder="e.g. Q4 2026 Enterprise Pricing & SLA"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
              />
            </div>

            <div>
              <label className="text-[11px] font-semibold text-slate-400">Category / Source</label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                className="w-full mt-1 p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
              >
                <option value="faq_manual">FAQ & Product Questions</option>
                <option value="pricing">Pricing & Subscription Plans</option>
                <option value="policy">Terms & Compliance Policies</option>
                <option value="technical">Technical Specs & Integrations</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-semibold text-slate-400">Document Text Content</label>
              <textarea
                rows={6}
                required
                placeholder="Paste product details, pricing tiers, refund policy, or customer answers here..."
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full mt-1 p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100 leading-relaxed resize-none"
              />
            </div>

            {statusMessage && (
              <p className="text-xs text-blue-300 font-medium">{statusMessage}</p>
            )}

            <button
              type="submit"
              disabled={ingesting || !title.trim() || !content.trim()}
              className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition shadow"
            >
              <Sparkles className="w-4 h-4" />
              <span>{ingesting ? "Vectorizing..." : "Ingest & Vectorize"}</span>
            </button>
          </form>
        </div>

        {/* Ingested Documents List */}
        <div className="lg:col-span-2 p-5 rounded-xl bg-slate-900/60 border border-border space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-indigo-400" /> Vector Indexed Documents ({documents.length})
            </h3>
            <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800 px-2 py-0.5 rounded">
              Qdrant Collection: Cosine 1536-dim
            </span>
          </div>

          <div className="space-y-3">
            {documents.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs space-y-2">
                <FileText className="w-8 h-8 text-slate-600 mx-auto" />
                <p>No knowledge documents indexed yet.</p>
                <p className="text-[11px] text-slate-600">
                  Use the form on the left to add your first product FAQ or pricing guide.
                </p>
              </div>
            ) : (
              documents.map((doc) => (
                <div
                  key={doc.id}
                  className="p-3.5 rounded-lg bg-slate-950/40 border border-slate-800 flex items-center justify-between hover:bg-slate-800/30 transition"
                >
                  <div>
                    <h4 className="text-xs font-semibold text-slate-100">{doc.title}</h4>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      Type: <span className="uppercase">{doc.source_type}</span> &bull; Indexed Chunks:{" "}
                      <strong className="text-indigo-400">{doc.total_chunks}</strong>
                    </p>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 uppercase flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> Ready
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
