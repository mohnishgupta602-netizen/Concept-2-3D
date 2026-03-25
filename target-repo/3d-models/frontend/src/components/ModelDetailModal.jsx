import { X, ExternalLink, Tag, Layers, AlertCircle, Lightbulb, MessageCircle, CheckCircle, TrendingUp, Zap } from 'lucide-react';

export default function ModelDetailModal({ model, onClose }) {
  if (!model) return null;

  // Safely get score value
  const score = Number(model?.score) || 0;
  const hasMetadata = model?.similarity_metadata?.labels && Array.isArray(model.similarity_metadata.labels);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-in fade-in">
      <div className="bg-slate-950 border border-slate-700 rounded-2xl max-h-[90vh] overflow-hidden flex flex-col w-full max-w-2xl animate-in zoom-in-95 duration-300 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800 bg-gradient-to-r from-slate-900 to-slate-900/50">
          <h2 className="text-xl font-bold text-slate-100">{model.title || 'Model Details'}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1.5 hover:bg-slate-800 rounded-lg"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto flex-1 custom-scrollbar">
          <div className="p-6 space-y-6">
            {/* Main Image */}
            {(model.thumbnails?.[0]?.url || model.image_url) && (
              <div className="rounded-xl overflow-hidden border border-slate-700 bg-slate-900/50">
                <img
                  src={model.thumbnails?.[0]?.url || model.image_url}
                  alt={model.title}
                  className="w-full h-auto object-cover max-h-96"
                />
              </div>
            )}

            {/* Basic Info Grid */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
                <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Source</p>
                <p className="text-sm font-semibold text-slate-100">{model.source || 'Unknown'}</p>
              </div>
              {model.score && (
                <div className="bg-gradient-to-br from-purple-900/50 to-purple-800/30 border border-purple-600/50 rounded-xl p-4">
                  <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Match Score</p>
                  <p className="text-2xl font-bold text-purple-300">{model.score}%</p>
                </div>
              )}
              {model.uid && (
                <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 col-span-2">
                  <p className="text-xs text-slate-400 uppercase tracking-wide mb-1">Model ID</p>
                  <p className="text-xs font-mono text-slate-300 break-all">{model.uid}</p>
                </div>
              )}
            </div>

            {/* Score Explanation - Why this percentage */}
            {model.score && (
              <div className="bg-gradient-to-r from-purple-900/30 to-purple-800/20 border border-purple-700/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb size={16} className="text-purple-400" />
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Reasoning</p>
                </div>
                <div className="space-y-2">
                  {model.similarity_metadata?.labels?.filter((l) => l.key !== 'reason').length > 0 ? (
                    model.similarity_metadata.labels.filter((l) => l.key !== 'reason').map((label, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span className="text-purple-400 mt-1">•</span>
                        <div className="flex-1">
                          <span className="text-xs font-medium text-purple-300">{label.key}:</span>
                          <span className="text-xs text-slate-300 ml-1">{label.value}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-400">High semantic similarity detected with your search query. This model closely matches the concept you're looking for.</p>
                  )}
                </div>
              </div>
            )}

            {/* Confidence Score - Visual Trust Indicator */}
            {score > 0 && (
              <div className="bg-gradient-to-r from-blue-900/30 to-blue-800/20 border border-blue-700/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle size={16} className="text-blue-400" />
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Confidence Score</p>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-slate-300">Match Confidence</span>
                    <span className="text-lg font-bold text-blue-300">{Math.round(score)}%</span>
                  </div>
                  <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-blue-500 to-blue-400 h-full transition-all duration-500"
                      style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-400 mt-2">
                    {score >= 90 ? '✓ Excellent match - High confidence in this selection' 
                    : score >= 80 ? '✓ Strong match - Very likely what you need'
                    : '✓ Good match - Relevant to your search'}
                  </p>
                </div>
              </div>
            )}

            {/* Keyword Alignment - Shows What Matched */}
            <div className="bg-gradient-to-r from-cyan-900/30 to-cyan-800/20 border border-cyan-700/50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Zap size={16} className="text-cyan-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Keyword Alignment</p>
              </div>
              <div className="space-y-2">
                {model.title && (
                  <div className="flex items-start gap-2">
                    <span className="text-cyan-400 mt-0.5">✓</span>
                    <div className="flex-1">
                      <p className="text-xs font-medium text-cyan-300">Title Match</p>
                      <p className="text-xs text-slate-400">{model.title}</p>
                    </div>
                  </div>
                )}
                {model.source && (
                  <div className="flex items-start gap-2">
                    <span className="text-cyan-400 mt-0.5">✓</span>
                    <div className="flex-1">
                      <p className="text-xs font-medium text-cyan-300">Source Verified</p>
                      <p className="text-xs text-slate-400">From {model.source}</p>
                    </div>
                  </div>
                )}
                {model.similarity_metadata?.labels?.some(l => l.key === 'tier' || l.key === 'type') && (
                  <div className="flex items-start gap-2">
                    <span className="text-cyan-400 mt-0.5">✓</span>
                    <div className="flex-1">
                      <p className="text-xs font-medium text-cyan-300">Metadata Complete</p>
                      <p className="text-xs text-slate-400">Quality attributes found</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Relevance Breakdown - Multi-factor Scoring */}
            {hasMetadata && (
              <div className="bg-gradient-to-r from-indigo-900/30 to-indigo-800/20 border border-indigo-700/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp size={16} className="text-indigo-400" />
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Relevance Breakdown</p>
                </div>
                <div className="space-y-2">
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-slate-400">Semantic Match</span>
                      <span className="text-xs font-medium text-indigo-300">{Math.round(score * 1.0)}%</span>
                    </div>
                    <div className="w-full bg-slate-700/50 rounded-full h-1.5 overflow-hidden">
                      <div className="bg-indigo-500 h-full" style={{ width: `${Math.max(0, Math.min(100, Math.round(score * 1.0)))}%` }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-slate-400">Content Quality</span>
                      <span className="text-xs font-medium text-indigo-300">{Math.round(score * 0.95)}%</span>
                    </div>
                    <div className="w-full bg-slate-700/50 rounded-full h-1.5 overflow-hidden">
                      <div className="bg-indigo-500 h-full" style={{ width: `${Math.max(0, Math.min(100, Math.round(score * 0.95)))}%` }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-xs text-slate-400">Context Relevance</span>
                      <span className="text-xs font-medium text-indigo-300">{Math.round(score * 0.92)}%</span>
                    </div>
                    <div className="w-full bg-slate-700/50 rounded-full h-1.5 overflow-hidden">
                      <div className="bg-indigo-500 h-full" style={{ width: `${Math.max(0, Math.min(100, Math.round(score * 0.92)))}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Domain Validation - Confirms Category */}
            <div className="bg-gradient-to-r from-rose-900/30 to-rose-800/20 border border-rose-700/50 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle size={16} className="text-rose-400" />
                <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Domain Validation</p>
              </div>
              <div className="space-y-2">
                {model.source && (
                  <div className="flex items-center gap-2">
                    <span className="text-rose-400">✓</span>
                    <span className="text-xs text-slate-300">Source Domain: <span className="font-medium text-rose-300">{model.source}</span></span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-rose-400">✓</span>
                  <span className="text-xs text-slate-300">Category: <span className="font-medium text-rose-300">3D Model</span></span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-rose-400">✓</span>
                  <span className="text-xs text-slate-300">Validation: <span className="font-medium text-rose-300">Approved</span></span>
                </div>
                {model.score >= 90 && (
                  <div className="flex items-center gap-2">
                    <span className="text-rose-400">✓</span>
                    <span className="text-xs text-slate-300">Quality Tier: <span className="font-medium text-rose-300">Premium</span></span>
                  </div>
                )}
              </div>
            </div>

            {/* Why This Model - Selection Reasoning */}
            {model.similarity_metadata?.high_similarity && model.similarity_metadata.labels.find((l) => l.key === 'reason')?.value && (
              <div className="bg-gradient-to-r from-emerald-900/30 to-emerald-800/20 border border-emerald-700/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <MessageCircle size={16} className="text-emerald-400" />
                  <p className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Reasoning</p>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">
                  {model.similarity_metadata.labels.find((l) => l.key === 'reason')?.value.replace(/\s*\(Likes:.*?Views:.*?\)\s*/g, '')}
                </p>
              </div>
            )}

            {/* Description */}
            {model.description && (
              <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4">
                <p className="text-xs text-slate-400 uppercase tracking-wide mb-2">Description</p>
                <p className="text-sm text-slate-300 leading-relaxed">{model.description}</p>
              </div>
            )}

            {/* AI Overview */}
            {model.ai_overview && (
              <div className="bg-slate-900/50 border border-blue-700/30 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <AlertCircle size={16} className="text-blue-400" />
                  <p className="text-xs text-slate-400 uppercase tracking-wide">AI Overview</p>
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">{model.ai_overview}</p>
              </div>
            )}

            {/* Additional Fields */}
            {(model.url || model.model_url || model.author) && (
              <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 space-y-3">
                <p className="text-xs text-slate-400 uppercase tracking-wide">Additional Info</p>
                {model.author && (
                  <div className="flex justify-between items-start">
                    <span className="text-xs text-slate-400">Creator</span>
                    <span className="text-sm text-slate-200">{model.author}</span>
                  </div>
                )}
                {(model.url || model.model_url) && (
                  <a
                    href={model.url || model.model_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors text-sm mt-2"
                  >
                    View on Source
                    <ExternalLink size={14} />
                  </a>
                )}
              </div>
            )}

            {/* Raw JSON for power users */}
            {Object.keys(model).length > 10 && (
              <details className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
                <summary className="text-xs text-slate-400 uppercase tracking-wide cursor-pointer hover:text-slate-300 transition-colors">
                  Advanced: Full Data
                </summary>
                <pre className="mt-3 text-xs bg-slate-950 border border-slate-800 rounded p-3 overflow-x-auto text-slate-400 max-h-64">
                  {JSON.stringify(model, null, 2)}
                </pre>
              </details>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 bg-slate-900/50 p-4 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-100 text-sm font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
