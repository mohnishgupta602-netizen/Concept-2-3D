import React, { useEffect, useState } from 'react';
import ModelViewer from './ModelViewer';
import './index.css';

const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8010').replace(/\/$/, '');

function App() {
  const [concept, setConcept] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lang, setLang] = useState("en-US");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [userRating, setUserRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [avgRating, setAvgRating] = useState(null);

  const fetchPartLabels = async (modelId, conceptValue) => {
    if (!modelId) return null;
    try {
      const url = `${API_BASE_URL}/part-labels/${encodeURIComponent(modelId)}?auto_generate=true&concept=${encodeURIComponent(conceptValue || concept || '')}`;
      const res = await fetch(url);
      if (!res.ok) return null;
      const payload = await res.json();
      return payload?.part_labels || null;
    } catch (err) {
      console.error('Failed to fetch labels:', err);
      return null;
    }
  };

  const handleSearch = async (e, directQuery = null) => {
    if (e) e.preventDefault();
    const activeQuery = directQuery || concept;
    if (!activeQuery) return;

    setLoading(true);
    setError("");
    setResult(null);
    setChatMessages([]);
    setChatInput("");
    setUserRating(0);
    setHoverRating(0);
    setRatingSubmitted(false);
    setAvgRating(null);
    window.speechSynthesis.cancel();

    try {
      // Model generation endpoint can take some time depending on search/download
      const res = await fetch(`${API_BASE_URL}/visualize?concept=${encodeURIComponent(activeQuery)}`);
      if (!res.ok) throw new Error("Failed to generate model");
      const data = await res.json();
      let enriched = { ...data, query_concept: activeQuery };

      const inlineLabels = data?.part_labels?.parts || data?.data?.part_labels?.parts;
      const modelId = data?.metadata?.model_id || data?.data?.model_id;
      if ((!inlineLabels || inlineLabels.length === 0) && modelId) {
        const fetchedLabels = await fetchPartLabels(modelId, activeQuery);
        if (fetchedLabels?.parts?.length) {
          enriched = {
            ...enriched,
            part_labels: fetchedLabels,
            data: { ...(enriched.data || {}), part_labels: fetchedLabels }
          };
        }
      }

      setResult(enriched);
      setConcept(activeQuery);
      
      // Fetch average rating if model exists
      if (data.data?.uid || data.metadata?.name) {
        fetchAvgRating(data.data?.uid || data.metadata?.name);
      }
    } catch (err) {
      console.error(err);
      setError("Error connecting to Engine Backend / AI Generation Timeout.");
    } finally {
      setLoading(false);
    }
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError("");
    setResult(null);
    window.speechSynthesis.cancel();

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData
      });
      if (!res.ok) throw new Error("Image classification failed");
      
      const data = await res.json();
      const detectedConcept = data.concept;
      
      // Auto-trigger the visualization process for the detected concept
      await handleSearch(null, detectedConcept);
      
    } catch (err) {
      console.error(err);
      setError("Error analyzing image.");
      setLoading(false);
    }
    
    // reset file input
    e.target.value = null;
  };

  const handleReset = () => {
    setResult(null);
    setConcept("");
    setError("");
    setChatMessages([]);
    setChatInput("");
    window.speechSynthesis.cancel();
  };

  useEffect(() => {
    if (!result) return;

    const baseConcept = result.query_concept || "this concept";
    const intro = result.ai_overview
      ? `I can answer follow-up questions about "${baseConcept}". Ask anything about this idea or generated model.`
      : `I can answer follow-up questions about "${baseConcept}". Information may be limited for this concept.`;

    setChatMessages([
      {
        role: "assistant",
        text: intro
      }
    ]);
  }, [result]);

  const handleAskAgent = async () => {
    const question = chatInput.trim();
    if (!question || !result || chatLoading) return;

    const userMessage = { role: "user", text: question };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/agent/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept: result.query_concept,
          question,
          model_name: result.data?.name || result.metadata?.name || null
        })
      });

      if (!res.ok) throw new Error("Agent request failed");

      const data = await res.json();
      const answer = data.answer || "I could not produce an answer from Wikipedia context.";

      setChatMessages((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch (err) {
      console.error(err);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "I couldn't reach the AI agent right now. Please try again."
        }
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleChatKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAskAgent();
    }
  };
  
  const handleDownload = () => {
    const viewerUrl = result?.data?.viewer || result?.model_url;
    if (viewerUrl) {
      // Directs user to download the generated .glb file served locally
      window.open(viewerUrl, '_blank');
    }
  };

  const fetchAvgRating = async (modelId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/feedback/${modelId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.avg_rating) {
          setAvgRating(data.avg_rating);
        }
      }
    } catch (err) {
      console.error("Failed to fetch rating:", err);
    }
  };

  const handleRatingSubmit = async (rating) => {
    const modelId = result?.data?.uid || result?.metadata?.name || result?.query_concept;
    if (!modelId) return;
    
    try {
      const res = await fetch(`${API_BASE_URL}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_id: modelId,
          user_id: 'anonymous_user',
          rating: rating,
          comment: ''
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        setRatingSubmitted(true);
        setAvgRating(data.avg_rating);
        setUserRating(rating);
      }
    } catch (err) {
      console.error("Failed to submit rating:", err);
    }
  };

  const renderStars = () => {
    const stars = [];
    const displayRating = hoverRating || userRating || 0;
    
    for (let i = 1; i <= 5; i++) {
      const isHalf = displayRating >= i - 0.5 && displayRating < i;
      const isFull = displayRating >= i;
      
      stars.push(
        <span
          key={i}
          className="star"
          onMouseEnter={() => !ratingSubmitted && setHoverRating(i)}
          onMouseLeave={() => setHoverRating(0)}
          onClick={() => !ratingSubmitted && handleRatingSubmit(i)}
          style={{
            cursor: ratingSubmitted ? 'default' : 'pointer',
            color: isFull ? '#ffd700' : isHalf ? '#ffd700' : '#444',
            fontSize: '1.5rem',
            marginRight: '0.2rem'
          }}
        >
          {isHalf ? '★' : '★'}
        </span>
      );
    }
    return stars;
  };

  const playAudioDescription = () => {
    window.speechSynthesis.cancel();

    let textToSpeak = (result?.ai_overview || "").trim();
    if (!textToSpeak) {
      textToSpeak =
        lang === "hi-IN"
          ? "इस कॉन्सेप्ट के लिए विकिपीडिया अवलोकन उपलब्ध नहीं है।"
          : "Wikipedia concept overview is not available for this concept.";
    }

    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    const voices = window.speechSynthesis.getVoices();
    const matchingVoice = voices.find(v => v.lang.includes(lang.split('-')[0]));
    if (matchingVoice) utterance.voice = matchingVoice;
    
    utterance.lang = lang;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <>
      <div className="bg-gradients">
        <div className="gradient-blob blob-1"></div>
        <div className="gradient-blob blob-2"></div>
        <div className="gradient-blob blob-3"></div>
        <div className="light-cone light-cone-left"></div>
        <div className="light-cone light-cone-right"></div>
        <div className="horizon-glow"></div>
      </div>

      <div className="app-container">
        <header>
          <h1 className="title">Concept3D<span style={{color: 'var(--accent)'}}>.</span>Generative</h1>
          <p className="subtitle">Zero-Dependency True Generative 3D AI (Powered by BlenderKit + FastAPI)</p>
        </header>

        <form onSubmit={handleSearch} className="search-container">
          <div className="search-hub">
            <input 
              className="search-input"
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              placeholder="Prompt to Generate (e.g. A flying car, Futuristic Chair...)"
              autoComplete="off"
            />
            <button type="submit" className="btn-primary" disabled={loading || !concept.trim()}>
              {loading ? 'Forging AI' : 'Generate'}
            </button>
          </div>
        </form>

        <div className="upload-btn-container">
          <div className="image-upload-wrapper">
            <button type="button" className="btn-upload">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
              Or Upload Image to Prompt AI
            </button>
            <input type="file" accept="image/png, image/jpeg, image/webp" onChange={handleImageUpload} disabled={loading} />
          </div>
        </div>

        {loading && (
          <div className="loader-container">
            <div className="spinner"></div>
            <p style={{color: 'var(--text-muted)', fontSize: '1.2rem'}}>Forging your custom 3D model via AI search pipeline...</p>
            <p style={{color: 'var(--accent)', marginTop: '0.5rem'}}>This typically takes 30 to 120 seconds. Please wait.</p>
          </div>
        )}

        {error && <div className="error-msg">{error}</div>}

        {result && !loading && (
          <main className="glass-panel">
            <div className="result-layout">
              <section className="result-main">
                {(() => {
                  const similarity = result?.similarity_score ?? result?.metadata?.final_similarity_score;
                  return typeof similarity === 'number' ? (
                    <div style={{ marginBottom: '0.8rem', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                      Similarity with searched concept: <strong style={{ color: 'var(--accent)' }}>{(similarity * 100).toFixed(1)}%</strong>
                    </div>
                  ) : null;
                })()}

                <div className="panel-header">
                  <div>
                    <h2 className="model-title">
                      {result?.data?.viewer
                        ? `${result.type === "retrieved" ? "Retrieved" : "Generated"}: ${result.data?.name || result.metadata?.name || result.query_concept}`
                        : `Fallback Geometry: ${result.query_concept}`}
                    </h2>
                    <div style={{marginTop: '0.5rem', display: 'flex', gap: '1rem', alignItems: 'center'}}>
                      <span>
                        <span className="status-dot"></span>
                        <span style={{color: 'var(--text-muted)', fontSize: '0.9rem'}}>
                          {result?.data?.viewer
                            ? (result.type === "retrieved" ? 'High-confidence retrieved 3D asset' : 'AI generated fallback 3D model')
                            : 'Generated Fallback Primitive'}
                        </span>
                      </span>

                      {result?.data?.viewer && result.data?.isDownloadable && (
                        <button className="btn-secondary btn-download" onClick={handleDownload} style={{padding: '0.3rem 0.8rem', fontSize: '0.85rem'}}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                          Direct Save .glb
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                <div className="controls-row">
                  <select
                    className="select-modern"
                    value={lang}
                    onChange={(e) => setLang(e.target.value)}
                  >
                    <option value="en-US">English Audio</option>
                    <option value="hi-IN">Hindi (हिंदी) Audio</option>
                  </select>

                  <button type="button" className="btn-secondary" onClick={playAudioDescription}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
                    Listen to Explanation
                  </button>

                  <button type="button" className="btn-secondary btn-danger" onClick={handleReset} style={{marginLeft: 'auto'}}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><polyline points="3 3 3 8 8 8"></polyline></svg>
                    Reset Viewer
                  </button>
                </div>

                {!(result?.fallback_2d_image_url && result?.fallback_2d_source === 'free_api') && (
                  <ModelViewer
                    data={result?.data?.viewer ? result.data : null}
                    fallbackShapes={result?.data?.viewer ? null : result.shapes}
                  />
                )}

                {!result?.data?.viewer && result?.fallback_2d_image_url && (
                  <div className="ai-info-card" style={{ marginTop: '1rem' }}>
                    <div className="ai-header">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                      Fallback 2D Preview
                    </div>

                    <img
                      src={result.fallback_2d_image_url}
                      alt={`Fallback blueprint for ${result?.query_concept || 'concept'}`}
                      style={{ width: '100%', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}
                    />
                  </div>
                )}

                {!result?.data?.viewer && !result?.fallback_2d_image_url && result?.geometry_details?.shapes?.length > 0 && (
                  <div className="ai-info-card" style={{ marginTop: '1rem' }}>
                    <div className="ai-header">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                      Fallback Geometry Details
                    </div>

                    <div className="ai-text" style={{ display: 'grid', gap: '0.55rem' }}>
                      {result.geometry_details.shapes.map((part, idx) => (
                        <div key={`${part?.name || 'geo'}-${idx}`} style={{ padding: '0.6rem 0.7rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
                          <div style={{ fontWeight: 700 }}>{(part?.primitive || 'shape').toUpperCase()}</div>
                          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                            Position: x={part?.position?.x ?? 0}, y={part?.position?.y ?? 0}, z={part?.position?.z ?? 0}
                          </div>
                          <div style={{ color: 'var(--accent)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                            Params: {Object.entries(part?.parameters || {}).map(([k, v]) => `${k}=${v}`).join(', ')}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(() => {
                  const parts = result?.part_labels?.parts || result?.data?.part_labels?.parts || [];
                  if (!parts.length) return null;
                  return (
                    <div className="ai-info-card" style={{ marginTop: '1rem' }}>
                      <div className="ai-header">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="7.5 4.21 12 6.81 16.5 4.21"></polyline><polyline points="7.5 19.79 7.5 14.6 3 12"></polyline><polyline points="21 12 16.5 14.6 16.5 19.79"></polyline><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                        Part Labels
                      </div>
                      <div className="ai-text" style={{ display: 'grid', gap: '0.6rem' }}>
                        {parts.slice(0, 10).map((part, idx) => (
                          <div key={`${part?.name || 'part'}-${idx}`} style={{ padding: '0.55rem 0.7rem', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px' }}>
                            <div style={{ fontWeight: 700, color: 'var(--text-bright)' }}>{part?.name || `part-${idx + 1}`}</div>
                            {part?.description && <div style={{ color: 'var(--text-muted)', fontSize: '0.92rem' }}>{part.description}</div>}
                            {part?.location && <div style={{ color: 'var(--accent)', fontSize: '0.85rem' }}>Location: {part.location}</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}

                {result.ai_overview && (
                  <div className="ai-info-card">
                    <div className="ai-header">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                      Wikipedia Concept Overview
                    </div>
                    <div className="ai-text">
                      {result.ai_overview}
                    </div>
                  </div>
                )}

                {/* Rating System */}
                <div className="rating-section" style={{marginTop: '1.5rem', padding: '1rem', background: 'rgba(0,0,0,0.2)', borderRadius: '8px'}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap'}}>
                    <div>
                      <div style={{fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.3rem'}}>
                        {ratingSubmitted ? 'Thank you for your rating!' : 'Rate this model:'}
                      </div>
                      <div style={{display: 'flex', alignItems: 'center'}}>
                        {renderStars()}
                      </div>
                    </div>
                    
                    {avgRating !== null && (
                      <div style={{marginLeft: 'auto', textAlign: 'right'}}>
                        <div style={{fontSize: '1.2rem', color: '#ffd700', fontWeight: 'bold'}}>
                          {avgRating.toFixed(1)} ★
                        </div>
                        <div style={{fontSize: '0.8rem', color: 'var(--text-muted)'}}>
                          Average Rating
                        </div>
                      </div>
                    )}
                  </div>
                  
                  {ratingSubmitted && (
                    <div style={{marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--accent)'}}>
                      Your feedback helps improve future model recommendations!
                    </div>
                  )}
                </div>
              </section>

              <aside className="agent-sidebar">
                <div className="agent-sidebar-header">
                  <h3>Concept Discussion &amp; Q&amp;A</h3>
                  <p>AI concept assistant</p>
                </div>

                <div className="agent-messages">
                  {chatMessages.map((msg, idx) => (
                    <div key={`${msg.role}-${idx}`} className={`agent-msg ${msg.role}`}>
                      <div className="agent-msg-role">{msg.role === "assistant" ? "AI" : "You"}</div>
                      <div className="agent-msg-text">{msg.text}</div>
                    </div>
                  ))}

                  {chatLoading && (
                    <div className="agent-msg assistant">
                      <div className="agent-msg-role">AI</div>
                      <div className="agent-msg-text">Thinking...</div>
                    </div>
                  )}
                </div>

                <div className="agent-input-row">
                  <textarea
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={handleChatKeyDown}
                    placeholder="Ask about the model idea..."
                    rows={2}
                    disabled={chatLoading}
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleAskAgent}
                    disabled={chatLoading || !chatInput.trim()}
                  >
                    Ask
                  </button>
                </div>
              </aside>
            </div>
          </main>
        )}
      </div>
    </>
  );
}

export default App;
