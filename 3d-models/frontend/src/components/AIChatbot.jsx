import { useState } from 'react';
import { Send, Bot, User } from 'lucide-react';
import { apiUrl } from '../config/api';

export default function AIChatbot() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: "Hi! I'm your Concept3D AI Agent. You can ask me anything about the model you're viewing!"
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const newUserMsg = { id: Date.now(), role: 'user', content: input };
    setMessages(prev => [...prev, newUserMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(apiUrl('/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: input,
          model_context: "3D Model Viewing" // Could be enhanced with actual model metadata
        })
      });
      const data = await response.json();
      
      if (data.status === 'success') {
        setMessages(prev => [...prev, {
          id: Date.now() + 1,
          role: 'assistant',
          content: data.message
        }]);
      } else {
        throw new Error(data.detail || 'Chat failed');
      }
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        content: "Sorry, I'm having trouble connecting to the AI service. Please ensure the backend is running."
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-slate-900/50 border border-slate-800/50 rounded-2xl shadow-xl backdrop-blur-sm h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-800/50 flex justify-between items-center bg-slate-800/30">
        <div className="flex items-center gap-2 font-semibold">
          <Bot size={20} className="text-primary-400" />
          <span>Design Assistant</span>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Live</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-grow overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
              msg.role === 'assistant' ? 'bg-indigo-900/50 border border-indigo-500/30' : 'bg-slate-700'
            }`}>
              {msg.role === 'assistant' ? <Bot size={16} className="text-indigo-400" /> : <User size={16} className="text-slate-300" />}
            </div>
            <div className={`max-w-[85%] p-3 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'assistant' 
                ? 'bg-slate-800/50 text-slate-200 border border-slate-700/50' 
                : 'bg-primary-600 text-white shadow-lg shadow-primary-900/20'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={handleSend} className="p-4 bg-slate-800/20 border-t border-slate-800/50">
        <div className="relative">
          <input
            type="text"
            placeholder="Ask about this model..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            className="w-full bg-slate-900/80 border border-slate-700 rounded-xl py-3 pl-4 pr-12 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-2 top-1.5 bottom-1.5 w-9 flex items-center justify-center bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}
