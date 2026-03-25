// ============================================================
//  TireTroopers — Lead Finder Component
//  Paste this into your Lovable leads section
//  Replace YOUR_RAILWAY_URL with your actual Railway URL
// ============================================================

import { useState } from "react";

const API_URL = "https://YOUR_RAILWAY_URL.railway.app"; // 👈 change this after deploying

const SEGMENT_OPTIONS = ["all","Fleet","Construction","Landscaping","Contractor","Delivery","Realtor"];
const WARMTH_OPTIONS  = ["all","hot","warm","cold"];

const WARMTH_STYLE = {
  hot:  { bg: "bg-red-100",    text: "text-red-600",    label: "🔥 Hot"  },
  warm: { bg: "bg-orange-100", text: "text-orange-500", label: "🟠 Warm" },
  cold: { bg: "bg-blue-100",   text: "text-blue-500",   label: "🔵 Cold" },
};

export default function LeadFinder() {
  const [leads,    setLeads]    = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [segment,  setSegment]  = useState("all");
  const [warmth,   setWarmth]   = useState("all");
  const [searched, setSearched] = useState(false);

  async function fetchLeads() {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ segment, warmth, limit: "150" });
      const res = await fetch(`${API_URL}/leads?${params}`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setLeads(data.leads || []);
      setSearched(true);
    } catch (e) {
      setError("Could not reach the lead API. Make sure your Railway server is running.");
    } finally {
      setLoading(false);
    }
  }

  function researchUrl(type, lead) {
    const biz = encodeURIComponent(lead.business + " Kamloops");
    const urls = {
      google:   `https://www.google.com/search?q=${biz}`,
      linkedin: `https://www.linkedin.com/search/results/all/?keywords=${biz}`,
      facebook: `https://www.facebook.com/search/top?q=${biz}`,
      maps:     `https://www.google.com/maps/search/${biz}`,
      yp:       `https://www.yellowpages.ca/search/si/1/${encodeURIComponent(lead.business)}/Kamloops+BC`,
    };
    return urls[type];
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">🛞 Lead Finder</h1>
        <p className="text-gray-500 mt-1">Real Kamloops businesses scraped live from directories</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
        <div>
          <label className="text-xs font-semibold text-gray-500 block mb-1">SEGMENT</label>
          <select
            value={segment}
            onChange={e => setSegment(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            {SEGMENT_OPTIONS.map(s => (
              <option key={s} value={s}>{s === "all" ? "All Segments" : s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-gray-500 block mb-1">WARMTH</label>
          <select
            value={warmth}
            onChange={e => setWarmth(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            {WARMTH_OPTIONS.map(w => (
              <option key={w} value={w}>{w === "all" ? "All" : w.charAt(0).toUpperCase() + w.slice(1)}</option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <button
            onClick={fetchLeads}
            disabled={loading}
            className="bg-orange-500 hover:bg-orange-600 text-white font-bold px-6 py-2 rounded-lg text-sm disabled:opacity-50 transition-colors"
          >
            {loading ? "Scraping..." : "🔍 Find Real Leads"}
          </button>
        </div>
        {leads.length > 0 && (
          <div className="flex items-end ml-auto">
            <span className="text-sm text-gray-500">{leads.length} leads found</span>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-4 text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-16">
          <div className="animate-spin text-4xl mb-4">🛞</div>
          <p className="text-gray-500 font-medium">Scraping Yellow Pages, Canada411 and Google...</p>
          <p className="text-gray-400 text-sm mt-2">This takes 30–60 seconds</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && searched && leads.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <div className="text-4xl mb-3">🔍</div>
          <p>No leads found for those filters. Try "All Segments".</p>
        </div>
      )}

      {/* Leads Table */}
      {!loading && leads.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Business</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Contact</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Segment</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Warmth</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Reason</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Research</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {leads.map((lead, i) => {
                const w = WARMTH_STYLE[lead.warmth] || WARMTH_STYLE.warm;
                return (
                  <tr key={i} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-gray-900">{lead.business}</div>
                      {lead.address && (
                        <div className="text-xs text-gray-400 mt-0.5">{lead.address}</div>
                      )}
                      {lead.rating && (
                        <div className="text-xs text-yellow-600 mt-0.5">{lead.rating}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {lead.phone && (
                        <a href={`tel:${lead.phone}`} className="text-orange-500 hover:underline font-medium block">
                          {lead.phone}
                        </a>
                      )}
                      {lead.website && (
                        <a href={lead.website} target="_blank" rel="noopener noreferrer"
                           className="text-blue-500 hover:underline text-xs block mt-0.5 truncate max-w-32">
                          {lead.website.replace(/^https?:\/\/(www\.)?/,'')}
                        </a>
                      )}
                      {!lead.phone && !lead.website && (
                        <span className="text-gray-300 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="bg-gray-100 text-gray-700 px-2 py-1 rounded-full text-xs font-medium">
                        {lead.segment}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-1.5 w-16">
                          <div
                            className="bg-orange-400 h-1.5 rounded-full"
                            style={{ width: `${lead.score}%` }}
                          />
                        </div>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${w.bg} ${w.text}`}>
                          {w.label}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 max-w-48">
                      {lead.reason}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {[
                          { key: "google",   label: "G",   bg: "#4285F4" },
                          { key: "linkedin", label: "in",  bg: "#0077B5" },
                          { key: "facebook", label: "f",   bg: "#1877F2" },
                          { key: "maps",     label: "📍",  bg: "#34A853" },
                          { key: "yp",       label: "YP",  bg: "#F5A623" },
                        ].map(btn => (
                          <a
                            key={btn.key}
                            href={researchUrl(btn.key, lead)}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ backgroundColor: btn.bg }}
                            className="inline-flex items-center justify-center w-6 h-6 rounded text-white text-xs font-bold no-underline"
                            title={btn.key}
                          >
                            {btn.label}
                          </a>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
