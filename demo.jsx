import React, { useState, useEffect } from 'react';

// Mock data
const mockClient = {
  name: "Stellar Roofing Sarasota",
  industry: "roofing",
  geo: "Sarasota, FL"
};

const mockCompetitors = [
  { id: 1, name: "JBS Roofing", domain: "jbsroofing.com", pages: 23, lastCrawl: "2 hours ago", newContent: 2 },
  { id: 2, name: "Western Roofing", domain: "westernroofing.com", pages: 18, lastCrawl: "4 hours ago", newContent: 0 },
  { id: 3, name: "RoofCrafters", domain: "roofcrafters.com", pages: 31, lastCrawl: "1 hour ago", newContent: 1 },
];

const mockQueue = [
  { 
    id: 1, 
    title: "Expert Roof Repair Sarasota - 10 Essential Tips from Licensed Pros",
    keyword: "roof repair sarasota",
    ourScore: 87,
    compScore: 62,
    wordCount: 1850,
    trigger: "JBS Roofing posted new content",
    status: "pending"
  },
  { 
    id: 2, 
    title: "Emergency Roof Repair Sarasota FL - 24/7 Storm Damage Response",
    keyword: "emergency roof repair sarasota",
    ourScore: 82,
    compScore: 58,
    wordCount: 1420,
    trigger: "RoofCrafters posted new content",
    status: "pending"
  },
];

const mockAlerts = [
  { id: 1, type: "new_content", title: "New content from JBS Roofing", message: "\"5 Signs You Need Roof Repair\" (920 words)", priority: "high", time: "12 min ago" },
  { id: 2, type: "rank_change", title: "Ranking improved!", message: "\"roof repair sarasota\" moved from #8 to #5", priority: "normal", time: "1 hour ago" },
  { id: 3, type: "content_ready", title: "Counter-content ready", message: "Review and approve your new blog post", priority: "high", time: "2 hours ago" },
];

const mockRankings = [
  { keyword: "roof repair sarasota", position: 5, change: 3, volume: 1200 },
  { keyword: "roofing company sarasota", position: 3, change: 1, volume: 880 },
  { keyword: "roof replacement sarasota", position: 8, change: -2, volume: 720 },
  { keyword: "emergency roof repair", position: 12, change: 5, volume: 440 },
  { keyword: "shingle repair sarasota", position: 4, change: 0, volume: 320 },
  { keyword: "tile roof repair", position: 15, change: 2, volume: 280 },
  { keyword: "flat roof repair sarasota", position: 7, change: 4, volume: 190 },
];

const mockContentBody = `
<h2>Roof Repair Sarasota: What Every Homeowner Needs to Know</h2>
<p>When it comes to <strong>roof repair in Sarasota, Florida</strong>, homeowners face unique challenges due to our humid climate and hurricane season. Our team at Stellar Roofing has been providing expert roof repair services for over 25 years.</p>

<h2>Top 10 Roof Repair Tips for Sarasota Homeowners</h2>
<p>Here are our professional recommendations for maintaining your roof and knowing when to call for roof repair in Sarasota.</p>

<h3>1. Schedule Regular Inspections</h3>
<p>Professional roof inspections should happen at least twice a year. In Sarasota, our humid climate makes this especially important.</p>

<h3>2. Address Leaks Immediately</h3>
<p>Water damage spreads quickly in Florida humidity. Contact a Sarasota roof repair specialist right away if you notice any signs of leaking.</p>

<h3>3. Keep Your Gutters Clean</h3>
<p>Clogged gutters cause water backup that damages your roof. We recommend cleaning gutters quarterly.</p>

<h2>Why Choose Stellar Roofing</h2>
<p>As a <strong>licensed and insured roofing contractor</strong> with 25 years of experience, we provide the highest quality roof repair services in Sarasota. We offer free estimates and stand behind our work with a satisfaction guarantee.</p>

<h2>Frequently Asked Questions</h2>
<h3>How much does roof repair cost in Sarasota?</h3>
<p>Roof repair costs typically range from $300 to $1,500 depending on the extent of damage. Contact us for a free estimate.</p>

<p><strong>Ready to get started?</strong> Contact Stellar Roofing today for expert <a href="/roof-repair/">roof repair</a>, <a href="/shingle-repair/">shingle repair</a>, and <a href="/emergency-repair/">emergency roofing services</a> in Sarasota, FL.</p>
`;

export default function RankCommanderDemo() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [selectedContent, setSelectedContent] = useState(null);
  const [queue, setQueue] = useState(mockQueue);
  const [crawling, setCrawling] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [competitors, setCompetitors] = useState(mockCompetitors);
  const [alerts, setAlerts] = useState(mockAlerts);
  const [demoStep, setDemoStep] = useState(0);

  const handleLogin = () => {
    setIsLoggingIn(true);
    setTimeout(() => {
      setIsLoggingIn(false);
      setIsLoggedIn(true);
    }, 1500);
  };

  const handleCrawl = (compId) => {
    setCrawling(compId);
    setTimeout(() => {
      setCrawling(null);
      // Simulate finding new content
      const newAlert = {
        id: Date.now(),
        type: "new_content",
        title: "New content detected!",
        message: "Found 2 new pages from competitor",
        priority: "high",
        time: "Just now"
      };
      setAlerts([newAlert, ...alerts]);
    }, 2000);
  };

  const handleApprove = (id) => {
    setQueue(queue.filter(q => q.id !== id));
    setSelectedContent(null);
    const newAlert = {
      id: Date.now(),
      type: "content_ready",
      title: "Content approved!",
      message: "Blog post saved and ready to publish",
      priority: "normal",
      time: "Just now"
    };
    setAlerts([newAlert, ...alerts]);
  };

  const getPositionColor = (pos) => {
    if (pos <= 3) return "bg-emerald-500";
    if (pos <= 5) return "bg-green-500";
    if (pos <= 10) return "bg-yellow-500";
    if (pos <= 20) return "bg-orange-500";
    return "bg-red-500";
  };

  // Login Screen
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-4">
        <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-8 w-full max-w-md border border-white/20">
          <div className="text-center mb-8">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-emerald-500 to-blue-600 flex items-center justify-center text-3xl">
              👑
            </div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-blue-400 bg-clip-text text-transparent">
              RankCommander AI
            </h1>
            <p className="text-gray-400 mt-2">Competitive Intelligence Dashboard</p>
          </div>
          
          <div className="space-y-4">
            <input 
              type="text" 
              defaultValue="https://mcp-framework.onrender.com"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500"
              placeholder="API URL"
            />
            <input 
              type="email" 
              defaultValue="admin@mcp.local"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500"
              placeholder="Email"
            />
            <input 
              type="password" 
              defaultValue="admin123"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-gray-500"
              placeholder="Password"
            />
            <button 
              onClick={handleLogin}
              disabled={isLoggingIn}
              className="w-full py-4 bg-gradient-to-r from-emerald-500 to-blue-600 rounded-xl text-white font-bold text-lg hover:opacity-90 transition disabled:opacity-50"
            >
              {isLoggingIn ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                  Authenticating...
                </span>
              ) : "Access Dashboard"}
            </button>
          </div>
          
          <p className="text-center text-gray-500 text-sm mt-6">
            Demo credentials pre-filled
          </p>
        </div>
      </div>
    );
  }

  // Content Preview Modal
  if (selectedContent) {
    return (
      <div className="min-h-screen bg-slate-900 p-4 overflow-auto">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white/5 backdrop-blur rounded-2xl overflow-hidden border border-white/10">
            {/* Header */}
            <div className="bg-gradient-to-r from-emerald-600 to-blue-600 p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex gap-2 mb-2">
                    <span className="px-3 py-1 bg-white/20 rounded-full text-sm text-white">Counter-Content</span>
                    <span className="px-3 py-1 bg-white/20 rounded-full text-sm text-white">SEO Score: {selectedContent.ourScore}</span>
                  </div>
                  <h2 className="text-xl font-bold text-white">{selectedContent.title}</h2>
                </div>
                <button 
                  onClick={() => setSelectedContent(null)}
                  className="p-2 hover:bg-white/20 rounded-lg text-white"
                >
                  ✕
                </button>
              </div>
            </div>
            
            {/* Score Comparison */}
            <div className="p-6 grid grid-cols-2 gap-4">
              <div className="bg-emerald-500/20 rounded-xl p-4 text-center">
                <p className="text-gray-400 text-sm">Our Score</p>
                <p className="text-4xl font-bold text-emerald-400">{selectedContent.ourScore}</p>
                <p className="text-emerald-400 text-sm">+{selectedContent.ourScore - selectedContent.compScore} points</p>
              </div>
              <div className="bg-orange-500/20 rounded-xl p-4 text-center">
                <p className="text-gray-400 text-sm">Competitor Score</p>
                <p className="text-4xl font-bold text-orange-400">{selectedContent.compScore}</p>
                <p className="text-orange-400 text-sm">We beat them! ✓</p>
              </div>
            </div>
            
            {/* Content */}
            <div className="p-6 border-t border-white/10">
              <div className="prose prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: mockContentBody }} />
            </div>
            
            {/* Actions */}
            <div className="p-4 border-t border-white/10 flex justify-between bg-white/5">
              <button 
                onClick={() => setSelectedContent(null)}
                className="px-6 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30"
              >
                ✕ Reject
              </button>
              <div className="flex gap-2">
                <button className="px-6 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20">
                  🔄 Regenerate
                </button>
                <button 
                  onClick={() => handleApprove(selectedContent.id)}
                  className="px-6 py-2 bg-gradient-to-r from-emerald-500 to-blue-600 text-white rounded-lg font-bold"
                >
                  ✓ Approve & Publish
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main Dashboard
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-950 to-slate-900 text-white">
      {/* Header */}
      <header className="bg-white/5 backdrop-blur border-b border-white/10 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-blue-600 flex items-center justify-center">
                👑
              </div>
              <div>
                <h1 className="font-bold">RankCommander AI</h1>
                <p className="text-sm text-gray-400">{mockClient.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/20 rounded-full">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="text-sm text-emerald-400">System Active</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="grid grid-cols-5 gap-3">
          {[
            { label: "Competitors", value: competitors.length, color: "emerald", icon: "🎯" },
            { label: "Keywords", value: mockRankings.length, color: "blue", icon: "🔑" },
            { label: "Content Ready", value: queue.length, color: "purple", icon: "📄" },
            { label: "Top 10", value: mockRankings.filter(r => r.position <= 10).length, color: "orange", icon: "🏆" },
            { label: "New Alerts", value: alerts.filter(a => a.priority === "high").length, color: "red", icon: "🔔" },
          ].map((stat, i) => (
            <div key={i} className={`bg-white/5 rounded-xl p-3 border border-white/10`}>
              <div className="flex items-center justify-between">
                <div>
                  <p className={`text-2xl font-bold text-${stat.color}-400`}>{stat.value}</p>
                  <p className="text-xs text-gray-400">{stat.label}</p>
                </div>
                <span className="text-2xl opacity-50">{stat.icon}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-4 pb-8">
        <div className="grid grid-cols-3 gap-4">
          
          {/* Competitors */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-bold flex items-center gap-2">
                <span className="text-emerald-400">🎯</span> Competitors
              </h2>
              <button 
                onClick={() => setShowAddModal(true)}
                className="px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded text-xs"
              >
                + Add
              </button>
            </div>
            
            {competitors.map(comp => (
              <div 
                key={comp.id} 
                onClick={() => handleCrawl(comp.id)}
                className="bg-white/5 rounded-xl p-3 border border-white/10 cursor-pointer hover:bg-white/10 transition"
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h3 className="font-medium">{comp.name}</h3>
                    <p className="text-xs text-gray-400">{comp.domain}</p>
                  </div>
                  {comp.newContent > 0 ? (
                    <span className="px-2 py-0.5 bg-red-500/20 text-red-400 rounded text-xs">
                      {comp.newContent} NEW
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded text-xs">
                      ✓ Monitored
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>📄 {comp.pages} pages</span>
                  <span>{crawling === comp.id ? "Scanning..." : `Last: ${comp.lastCrawl}`}</span>
                </div>
                {crawling === comp.id && (
                  <div className="mt-2 h-1 bg-white/10 rounded overflow-hidden">
                    <div className="h-full bg-emerald-500 animate-pulse" style={{width: "60%"}}></div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Content Queue */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-bold flex items-center gap-2">
                <span className="text-purple-400">⚡</span> Content Queue
              </h2>
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs">
                {queue.length} pending
              </span>
            </div>
            
            {queue.length === 0 ? (
              <div className="bg-white/5 rounded-xl p-6 text-center border border-white/10">
                <p className="text-gray-500">📥 No content pending</p>
              </div>
            ) : (
              queue.map(item => (
                <div 
                  key={item.id}
                  onClick={() => setSelectedContent(item)}
                  className="bg-white/5 rounded-xl p-3 border border-white/10 cursor-pointer hover:bg-white/10 transition"
                >
                  <div className="flex items-start justify-between mb-2">
                    <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs">
                      Counter-Content
                    </span>
                    <div className="flex items-center gap-1 text-sm">
                      <span className="text-emerald-400 font-bold">{item.ourScore}</span>
                      <span className="text-gray-500">vs</span>
                      <span className="text-orange-400">{item.compScore}</span>
                    </div>
                  </div>
                  <h3 className="text-sm font-medium mb-1 line-clamp-2">{item.title}</h3>
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>🔑 {item.keyword}</span>
                    <span>{item.wordCount} words</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Alerts & Rankings */}
          <div className="space-y-4">
            {/* Alerts */}
            <div className="space-y-2">
              <h2 className="font-bold flex items-center gap-2">
                <span className="text-red-400">🔔</span> Recent Alerts
              </h2>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {alerts.slice(0, 3).map(alert => (
                  <div key={alert.id} className="bg-white/5 rounded-lg p-2 border border-white/10">
                    <div className="flex items-start gap-2">
                      <span>{alert.priority === "high" ? "🔴" : "🟡"}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{alert.title}</p>
                        <p className="text-xs text-gray-400 truncate">{alert.message}</p>
                      </div>
                      <span className="text-xs text-gray-500 whitespace-nowrap">{alert.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Rankings */}
            <div className="space-y-2">
              <h2 className="font-bold flex items-center gap-2">
                <span className="text-blue-400">📈</span> Keyword Positions
              </h2>
              <div className="space-y-1.5 max-h-52 overflow-y-auto">
                {mockRankings.map((rank, i) => (
                  <div key={i} className="bg-white/5 rounded-lg p-2 flex items-center gap-2 border border-white/10">
                    <div className={`w-8 h-8 ${getPositionColor(rank.position)} rounded flex items-center justify-center font-bold text-white text-sm`}>
                      {rank.position}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate">{rank.keyword}</p>
                      <p className="text-xs text-gray-500">{rank.volume.toLocaleString()} /mo</p>
                    </div>
                    <div className="text-right">
                      {rank.change > 0 && <span className="text-emerald-400 text-sm">↑{rank.change}</span>}
                      {rank.change < 0 && <span className="text-red-400 text-sm">↓{Math.abs(rank.change)}</span>}
                      {rank.change === 0 && <span className="text-gray-500 text-sm">—</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
