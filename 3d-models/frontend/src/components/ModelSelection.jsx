import { Database, Check, FileText, Star } from 'lucide-react';

export default function ModelSelection({ results, currentModel, onSelect, onShowDetails }) {
  if (!results || results.length === 0) return null;

  return (
    <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl p-6 shadow-xl backdrop-blur-sm h-full flex flex-col">
      <div className="flex items-center gap-2 mb-6 text-slate-100 font-semibold">
        <Database size={20} className="text-purple-400" />
        <h3 className="text-lg">Model Selection ({results.length})</h3>
      </div>
      
      <div className="flex flex-col gap-3 overflow-y-auto pr-2 custom-scrollbar flex-grow">
        {results.map((res, index) => (
          <div key={index} className="flex flex-col gap-2">
            <button
              onClick={() => onSelect(res)}
              className={`text-left px-4 py-3 rounded-xl border transition-all duration-300 flex flex-col gap-2 group overflow-hidden relative cursor-pointer ${
                currentModel?.uid === res.uid 
                  ? 'bg-gradient-to-r from-purple-900/40 to-purple-800/30 border-purple-500/60 text-purple-100 shadow-[0_0_20px_rgba(168,85,247,0.25)]' 
                  : 'bg-slate-900/30 border-slate-800/60 text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 hover:border-slate-700/80 hover:shadow-[0_0_15px_rgba(100,116,139,0.1)]'
              }`}
            >
              {currentModel?.uid === res.uid && (
                <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-green-500/20 border border-green-500/60 flex items-center justify-center">
                  <Check size={12} className="text-green-400" />
                </div>
              )}
              
              <div className="flex justify-between items-start gap-2">
                <span className={`font-bold text-sm ${currentModel?.uid === res.uid ? 'text-purple-300' : 'text-slate-300 group-hover:text-slate-100'}`}>
                  {res.source}
                </span>
                <div className="flex gap-2 items-center">
                  {res.score && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      currentModel?.uid === res.uid
                        ? 'bg-purple-700/50 text-purple-200 border border-purple-600/50'
                        : 'bg-slate-800/60 text-slate-400 border border-slate-700'
                    }`}>
                      {res.score}%
                    </span>
                  )}
                  {res.average_rating > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium flex items-center gap-1 ${
                      currentModel?.uid === res.uid
                        ? 'bg-yellow-700/50 text-yellow-200 border border-yellow-600/50'
                        : 'bg-slate-800/60 text-yellow-400 border border-slate-700'
                    }`}>
                      <Star size={10} className="fill-current" />
                      {res.average_rating.toFixed(1)}
                    </span>
                  )}
                </div>
              </div>
              
              {(res.thumbnails?.[0]?.url || res.image_url) && (
                <div className="relative overflow-hidden rounded-lg h-24 bg-slate-800/50 border border-slate-700/50 mb-1">
                  <img
                    src={res.thumbnails?.[0]?.url || res.image_url}
                    alt={res.title}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950/40 via-transparent to-transparent" />
                </div>
              )}
              
              <span className="text-xs opacity-80 truncate line-clamp-1 italic">{res.title || 'Procedural Model'}</span>

              {Array.isArray(res.model_labels) && res.model_labels.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {res.model_labels.slice(0, 4).map((label) => (
                    <span
                      key={`${res.uid}-${label.key}`}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-sky-900/30 border border-sky-700/60 text-sky-200"
                    >
                      {label.key}: {label.value}
                    </span>
                  ))}
                </div>
              )}

              {res.similarity_metadata?.high_similarity && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {res.similarity_metadata.labels
                    .filter((label) => label.key !== 'reason')
                    .map((label) => (
                      <span
                        key={`${res.uid}-${label.key}`}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/35 border border-emerald-700/60 text-emerald-200"
                      >
                        {label.key}: {label.value}
                      </span>
                    ))}
                </div>
              )}
            </button>

            {currentModel?.uid === res.uid && (
              <button
                onClick={() => onShowDetails(res)}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/50 text-blue-300 hover:text-blue-200 text-xs font-medium transition-all duration-200"
              >
                <FileText size={14} />
                View Full Details
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
