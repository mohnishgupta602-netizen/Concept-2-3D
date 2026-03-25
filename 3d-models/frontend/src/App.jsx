import { useEffect, useMemo, useState } from 'react';
import SearchBar from './components/SearchBar';
import ThreeCanvas from './components/ThreeCanvas';
import ModelSelection from './components/ModelSelection';
import ModelDetailModal from './components/ModelDetailModal';
import AIChatbot from './components/AIChatbot';
import ReviewPanel from './components/ReviewPanel';
import { generateNarration, truncateNarrationToTime, calculateNarrationDuration } from './utils/narrationGenerator';
import { Layers, Square, Volume2 } from 'lucide-react';
import { apiUrl } from './config/api';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [modelData, setModelData] = useState(null);
  const [explodedValue, setExplodedValue] = useState(0);
  const [error, setError] = useState(null);
  const [resultsList, setResultsList] = useState([]);
  const [activeQuery, setActiveQuery] = useState('');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [detailedModel, setDetailedModel] = useState(null);
  const [rightPanelTab, setRightPanelTab] = useState('reviews');

  useEffect(() => {
    return () => {
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const narrationText = useMemo(() => {
    if (!modelData) return '';

    const topic = activeQuery || modelData.title || 'this concept';
    
    // Generate comprehensive narration
    let narration = generateNarration(topic, modelData, activeQuery);
    
    // Ensure it fits within 90-120 seconds constraint
    const duration = calculateNarrationDuration(narration);
    
    if (duration > 120) {
      // Truncate to fit within time constraint
      narration = truncateNarrationToTime(narration, 90, 120);
    }
    
    return narration;
  }, [modelData, activeQuery]);

  const narrationDuration = useMemo(() => {
    return calculateNarrationDuration(narrationText);
  }, [narrationText]);

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleReviewSubmitted = async () => {
    // Re-fetch review summaries for all models and resort
    if (resultsList.length === 0) return;

    try {
      const reviewSummaries = await Promise.all(
        resultsList.map(async (model) => {
          try {
            const res = await fetch(apiUrl(`/reviews/${encodeURIComponent(model.uid)}/summary`));
            if (res.ok) {
              const summaryData = await res.json();
              return { uid: model.uid, summary: summaryData.data };
            }
          } catch (err) {
            console.error(`Failed to fetch reviews for ${model.uid}:`, err);
          }
          return { uid: model.uid, summary: null };
        })
      );

      // Update results with new review data and resort
      const updatedResults = resultsList.map((model) => {
        const reviewData = reviewSummaries.find((r) => r.uid === model.uid);
        return {
          ...model,
          review_summary: reviewData?.summary || null,
          average_rating: reviewData?.summary?.avg_rating || 0,
        };
      }).sort((a, b) => {
        // Sort by average rating descending (highest first)
        return (b.average_rating || 0) - (a.average_rating || 0);
      });

      setResultsList(updatedResults);
      // Keep current model in view (don't change it just because order changed)
      if (modelData) {
        const updatedCurrentModel = updatedResults.find((m) => m.uid === modelData.uid);
        if (updatedCurrentModel) {
          setModelData(updatedCurrentModel);
        }
      }
    } catch (err) {
      console.error('Failed to re-sort models after review:', err);
    }
  };

  const stopNarration = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  };

  const playEnglishNarration = () => {
    if (!narrationText || !('speechSynthesis' in window)) return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(narrationText);
    utterance.lang = 'en-US';
    utterance.rate = 1;
    utterance.pitch = 1;

    const voices = window.speechSynthesis.getVoices();
    const englishVoice = voices.find((voice) => voice.lang && voice.lang.toLowerCase().startsWith('en'));
    if (englishVoice) utterance.voice = englishVoice;

    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const handleSearch = async (query) => {
    const cleanedQuery = (query || '').trim();
    setIsLoading(true);
    setError(null);
    setExplodedValue(0);
    setResultsList([]);
    setActiveQuery(cleanedQuery);
    stopNarration();
    
    try {
      // Parallel intent and search calls
      const [intentRes, searchRes] = await Promise.all([
        fetch(apiUrl('/intent'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query })
        }),
        fetch(apiUrl('/search'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query })
        })
      ]);

      const [_intentJson, searchJson] = await Promise.all([
        intentRes.json(),
        searchRes.json()
      ]);
      
      if (searchJson.status === 'success' || searchJson.status === 'fallback') {
        let data = Array.isArray(searchJson.data) ? searchJson.data : [searchJson.data];
        
        // Fetch review summaries for all models
        const reviewSummaries = await Promise.all(
          data.map(async (model) => {
            try {
              const res = await fetch(apiUrl(`/reviews/${encodeURIComponent(model.uid)}/summary`));
              if (res.ok) {
                const summaryData = await res.json();
                return { uid: model.uid, summary: summaryData.data };
              }
            } catch (err) {
              console.error(`Failed to fetch reviews for ${model.uid}:`, err);
            }
            return { uid: model.uid, summary: null };
          })
        );

        // Add review summary to each model and sort by average rating
        data = data.map((model) => {
          const reviewData = reviewSummaries.find((r) => r.uid === model.uid);
          return {
            ...model,
            review_summary: reviewData?.summary || null,
            average_rating: reviewData?.summary?.avg_rating || 0,
          };
        }).sort((a, b) => {
          // Sort by average rating descending (highest first)
          return (b.average_rating || 0) - (a.average_rating || 0);
        });

        setResultsList(data);
        setModelData(data[0]);
      } else {
        throw new Error(searchJson.message || 'Unknown error');
      }
    } catch (err) {
      console.error(err);
      setError('Failed to contact the backend. Ensure the API server is running and reachable.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center bg-[#0d1424] overflow-hidden text-slate-100 p-4">
      {/* Header Background Effects */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/5 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/5 blur-[120px] rounded-full pointer-events-none" />

      <header className="w-full max-w-[1400px] flex justify-between items-center mb-6 z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Layers className="text-white w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            Concept3D
          </h1>
        </div>
      </header>

      <main className="w-full max-w-[1440px] flex-grow flex flex-col z-10 relative overflow-hidden">
        {/* Tagline section (now always visible but can shrink) */}
        <div className={`text-center transition-all duration-700 ${modelData ? 'mb-4' : 'mb-8 py-10'}`}>
          <h2 className={`${modelData ? 'text-3xl' : 'text-5xl md:text-6xl'} font-black mb-4 tracking-tighter leading-tight bg-clip-text text-transparent bg-gradient-to-b from-white to-slate-500`}>
            Think it. <span className="text-blue-500">See it.</span> Explore it.
          </h2>
          {!modelData && (
            <p className="text-slate-400 text-lg md:text-xl max-w-2xl mx-auto leading-relaxed">
              An intelligent pipeline that bridges abstract text and spatial reality.<br/>
              Enter a concept to generate an interactive 3D model.
            </p>
          )}
        </div>

        <div className="w-full max-w-2xl mx-auto mb-6">
          <SearchBar onSearch={handleSearch} isLoading={isLoading} />
        </div>

        {error && (
          <div className="w-full max-w-2xl mx-auto mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-xl text-red-400 text-center">
            {error}
          </div>
        )}

        {modelData && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 w-full h-[calc(100vh-320px)] animate-in fade-in zoom-in-95 duration-700">
            {/* Left Sidebar: Model Selection */}
            <div className="lg:col-span-1 h-full overflow-hidden">
              <ModelSelection 
                results={resultsList} 
                currentModel={modelData} 
                onSelect={(m) => {
                  stopNarration();
                  setModelData(m);
                }}
                onShowDetails={(m) => {
                  setDetailedModel(m);
                }}
              />
            </div>

            {/* Main Canvas: 3D Viewer */}
            <div className="lg:col-span-2 h-full bg-slate-900/40 border border-slate-800/60 rounded-3xl overflow-hidden relative group">
              <ThreeCanvas modelData={modelData} explodedValue={explodedValue} />
              
              {/* Overlay info if needed */}
              <div className="absolute top-4 left-4 p-3 bg-slate-900/80 backdrop-blur rounded-xl border border-slate-800 opacity-0 group-hover:opacity-100 transition-opacity">
                 <h4 className="text-sm font-bold text-slate-100">{modelData.title || 'Selected Model'}</h4>
                 <p className="text-xs text-slate-400">Source: {modelData.source}</p>
              </div>
            </div>

            {/* Right Sidebar: Reviews & Chat */}
            <div className="lg:col-span-1 h-full overflow-hidden flex flex-col gap-4">
              <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl p-4 shadow-xl backdrop-blur-sm">
                <div className="flex items-center justify-between mb-3 text-slate-100 font-semibold">
                  <div className="flex items-center gap-2">
                    <Volume2 size={18} className="text-blue-400" />
                    <h3 className="text-sm">English Audio Description</h3>
                  </div>
                  {narrationText && (
                    <span className="text-xs text-slate-400 bg-slate-800/50 px-2 py-1 rounded">
                      {formatDuration(narrationDuration)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={playEnglishNarration}
                    disabled={!narrationText}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
                  >
                    <Volume2 size={15} />
                    {isSpeaking ? 'Replay' : 'Listen'}
                  </button>
                  <button
                    type="button"
                    onClick={stopNarration}
                    disabled={!isSpeaking}
                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-100 text-sm font-medium transition-colors"
                  >
                    <Square size={14} />
                    Stop
                  </button>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex items-center gap-1 border-b border-slate-800/50 bg-slate-950/20 rounded-t-lg px-1">
                <button
                  onClick={() => setRightPanelTab('reviews')}
                  className={`relative px-4 py-2.5 text-xs font-semibold transition-all duration-300 ${
                    rightPanelTab === 'reviews'
                      ? 'text-blue-300'
                      : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  Reviews
                  {rightPanelTab === 'reviews' && (
                    <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-gradient-to-r from-blue-500 to-blue-400 rounded-t transition-all duration-300" />
                  )}
                </button>
                <button
                  onClick={() => setRightPanelTab('chat')}
                  className={`relative px-4 py-2.5 text-xs font-semibold transition-all duration-300 ${
                    rightPanelTab === 'chat'
                      ? 'text-blue-300'
                      : 'text-slate-400 hover:text-slate-300'
                  }`}
                >
                  Chat
                  {rightPanelTab === 'chat' && (
                    <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-gradient-to-r from-blue-500 to-blue-400 rounded-t transition-all duration-300" />
                  )}
                </button>
              </div>

              {/* Tab Content with smooth transition */}
              <div className="flex-1 min-h-0 overflow-hidden relative">
                <div
                  className="absolute inset-0 transition-opacity duration-300 ease-in-out"
                  style={{ opacity: rightPanelTab === 'reviews' ? 1 : 0, pointerEvents: rightPanelTab === 'reviews' ? 'auto' : 'none' }}
                >
                  <ReviewPanel 
                    modelId={modelData?.uid} 
                    modelTitle={modelData?.title}
                    onReviewSubmitted={handleReviewSubmitted}
                  />
                </div>
                <div
                  className="absolute inset-0 transition-opacity duration-300 ease-in-out"
                  style={{ opacity: rightPanelTab === 'chat' ? 1 : 0, pointerEvents: rightPanelTab === 'chat' ? 'auto' : 'none' }}
                >
                  <AIChatbot />
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Model Detail Modal */}
      <ModelDetailModal 
        model={detailedModel}
        onClose={() => setDetailedModel(null)}
      />
    </div>
  );
}

export default App;
