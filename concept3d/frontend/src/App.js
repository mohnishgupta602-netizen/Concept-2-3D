import React, { useEffect, useState } from 'react';
import ModelViewer from './ModelViewer';
import './index.css';

function App() {
  const [concept, setConcept] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lang, setLang] = useState("en-US");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const handleSearch = async (e, directQuery = null) => {
    if (e) e.preventDefault();
    const activeQuery = directQuery || concept;
    if (!activeQuery) return;

    setLoading(true);
    setError("");
    setResult(null);
    setChatMessages([]);
    setChatInput("");
    window.speechSynthesis.cancel();

    try {
      // Model generation endpoint can take some time depending on search/download
      const res = await fetch(`http://localhost:8000/visualize?concept=${encodeURIComponent(activeQuery)}`);
      if (!res.ok) throw new Error("Failed to generate model");
      const data = await res.json();
      setResult({ ...data, query_concept: activeQuery });
      setConcept(activeQuery);
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
      const res = await fetch(`http://localhost:8000/upload`, {
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
      const res = await fetch("http://localhost:8000/agent/ask", {
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

                <ModelViewer
                  data={result?.data?.viewer ? result.data : null}
                  fallbackShapes={result?.data?.viewer ? null : result.shapes}
                />

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
