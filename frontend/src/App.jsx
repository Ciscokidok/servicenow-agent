import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './styles/App.css';

function App() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchHistory, setSearchHistory] = useState([]);

  useEffect(() => {
    const savedHistory = localStorage.getItem('searchHistory');
    if (savedHistory) {
      setSearchHistory(JSON.parse(savedHistory));
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.get('http://localhost:8000/api/search_snow', {
        params: {
          search_query: query,
          max_results: 100
        }
      });
      
      const newHistory = [{ query, timestamp: new Date().toISOString() }, ...searchHistory];
      setSearchHistory(newHistory);
      localStorage.setItem('searchHistory', JSON.stringify(newHistory));
      
      setResults(response.data);
    } catch (err) {
      const errorMessage = err.response 
        ? err.response.data.error || 'An error occurred'
        : err.message;
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>ServiceNow Query Tool</h1>
      </header>

      <main className="app-main">
        <form onSubmit={handleSubmit} className="search-form">
          <div className="search-input-container">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter your query (e.g., 'open change tickets' or 'change tickets created on 2025-05-09')"
              className="search-input"
            />
            <button type="submit" disabled={loading} className="search-button">
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {error && <div className="error-message">{error}</div>}

        {results && results.success && results.data && (
          <div className="results-container">
            <h2>Results</h2>
            <p className="result-count">Total Records: {results.data.length}</p>
            
            <table className="results-table">
              <thead>
                <tr>
                  <th>Number</th>
                  <th>Short Description</th>
                  <th>State</th>
                  <th>Opened At</th>
                  <th>Assigned To</th>
                </tr>
              </thead>
              <tbody>
                {results.data.map((record) => (
                  <tr key={record.number} className="record-row">
                    <td>{record.number}</td>
                    <td className="description-cell">{record.short_description}</td>
                    <td>{record.state}</td>
                    <td>{formatDate(record.opened_at)}</td>
                    <td>{record.assigned_to?.display_value || 'Unassigned'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="search-history">
          <h2>Search History</h2>
          <ul className="history-list">
            {searchHistory.map((historyItem, index) => (
              <li key={index} className="history-item">
                <span className="history-query">{historyItem.query}</span>
                <span className="history-timestamp">
                  {new Date(historyItem.timestamp).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </main>
    </div>
  );
}

export default App;
