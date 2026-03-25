import { useState } from 'react';
import { Search } from 'lucide-react';

export default function SearchBar({ onSearch, isLoading }) {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSearch(query);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto my-8 relative z-10">
      <form onSubmit={handleSubmit} className="relative flex items-center">
        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
          <Search className={`h-5 w-5 ${isLoading ? 'text-primary-500 animate-pulse' : 'text-slate-400'}`} />
        </div>
        <input
          type="text"
          className="block w-full pl-12 pr-4 py-4 bg-slate-800/80 backdrop-blur-md border border-slate-700 rounded-2xl leading-5 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 sm:text-lg transition-all shadow-xl"
          placeholder="What do you want to explore? e.g. 'Human Heart'"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={isLoading}
        />
        <button
          type="submit"
          disabled={!query.trim() || isLoading}
          className="absolute right-2 top-2 bottom-2 px-6 bg-primary-500 hover:bg-primary-600 text-white rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Generating...' : 'Generate 3D'}
        </button>
      </form>
    </div>
  );
}
