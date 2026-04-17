import { useEffect, useMemo, useState } from 'react';
import MapView from './components/MapView';
import RiskCard from './components/RiskCard';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function fetchLayer(layerName) {
  const response = await fetch(`${API_BASE}/layers/${layerName}`);
  if (!response.ok) {
    throw new Error(`Failed to load ${layerName} layer`);
  }
  return response.json();
}

export default function App() {
  const [latitude, setLatitude] = useState('12.9720');
  const [longitude, setLongitude] = useState('77.5950');
  const [report, setReport] = useState(null);
  const [layers, setLayers] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const parsedLat = useMemo(() => Number(latitude), [latitude]);
  const parsedLng = useMemo(() => Number(longitude), [longitude]);

  useEffect(() => {
    const loadLayers = async () => {
      try {
        const [water, forest, restricted] = await Promise.all([
          fetchLayer('water'),
          fetchLayer('forest'),
          fetchLayer('restricted'),
        ]);
        setLayers({ water, forest, restricted });
      } catch (loadError) {
        setError(loadError.message);
      }
    };

    loadLayers();
  }, []);

  const analyzeLocation = async (event) => {
    event.preventDefault();
    setError('');

    if (Number.isNaN(parsedLat) || Number.isNaN(parsedLng)) {
      setError('Latitude and longitude must be valid numbers.');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/analyze-location`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ latitude: parsedLat, longitude: parsedLng }),
      });

      if (!response.ok) {
        throw new Error('Analysis request failed. Verify backend is running.');
      }

      const data = await response.json();
      setReport(data);
    } catch (requestError) {
      setError(requestError.message);
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">
      <header className="mb-7">
        <p className="font-display text-sm uppercase tracking-[0.24em] text-cyan-200/85">
          AI Geospatial Validation
        </p>
        <h1 className="mt-1 max-w-3xl font-display text-3xl leading-tight text-white md:text-4xl">
          AI Land Safety Validation System
        </h1>
      </header>

      <section className="mb-6 rounded-2xl border border-cyan-100/20 bg-slate-900/70 p-5 shadow-panel">
        <form onSubmit={analyzeLocation} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label className="block">
            <span className="text-xs uppercase tracking-[0.16em] text-slate-300">Latitude</span>
            <input
              type="number"
              step="any"
              value={latitude}
              onChange={(event) => setLatitude(event.target.value)}
              className="mt-2 w-full rounded-lg border border-cyan-100/20 bg-slate-950/70 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-300"
              placeholder="12.9716"
              required
            />
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-[0.16em] text-slate-300">Longitude</span>
            <input
              type="number"
              step="any"
              value={longitude}
              onChange={(event) => setLongitude(event.target.value)}
              className="mt-2 w-full rounded-lg border border-cyan-100/20 bg-slate-950/70 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-300"
              placeholder="77.5946"
              required
            />
          </label>

          <button
            type="submit"
            disabled={loading}
            className="h-11 rounded-lg bg-cyan-300 px-5 font-semibold text-slate-900 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-cyan-300/50"
          >
            {loading ? 'Analyzing...' : 'Analyze Location'}
          </button>
        </form>
      </section>

      <section className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <MapView
          latitude={Number.isNaN(parsedLat) ? 12.9716 : parsedLat}
          longitude={Number.isNaN(parsedLng) ? 77.5946 : parsedLng}
          layers={layers}
        />
        <RiskCard result={report} loading={loading} error={error} />
      </section>
    </main>
  );
}
