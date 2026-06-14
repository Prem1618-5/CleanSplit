import { useState, FormEvent } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { importApi } from '../api';

export default function ImportPage() {
  const { id } = useParams<{ id: string }>();
  const gid = Number(id);
  const navigate = useNavigate();

  const [file, setFile] = useState<File | null>(null);
  const [rate, setRate] = useState('85');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true); setError('');
    try {
      const r = await importApi.upload(gid, parseFloat(rate), file);
      navigate(`/import/${r.data.session_id}/review`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || JSON.stringify(err?.response?.data) || 'Upload failed');
      setLoading(false);
    }
  };

  return (
    <div className="page" style={{ maxWidth: 620 }}>
      <Link to={`/groups/${id}`} className="text-muted text-sm">← Back to group</Link>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 8, marginBottom: 4 }}>
        Import expenses_export.csv
      </h1>
      <p className="text-muted text-sm mb-2">
        The importer detects data problems automatically. You'll review every anomaly
        before anything is written to the database.
      </p>

      <div className="card">
        <form onSubmit={submit}>
          <div className="form-group">
            <label>CSV file</label>
            <input
              type="file"
              accept=".csv"
              className="input"
              onChange={e => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>

          <div className="form-group">
            <label>USD → INR exchange rate</label>
            <input
              className="input"
              type="number"
              step="0.01"
              min="1"
              value={rate}
              onChange={e => setRate(e.target.value)}
              required
            />
            <p className="text-sm text-muted mt-1">
              Used to convert all USD expenses to ₹ for balance calculations.
              Approximate March 2026 rate: 85–87. Adjust if you know the exact rate.
            </p>
          </div>

          <div className="card" style={{ background: 'var(--bg)', marginBottom: 16 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>What the importer detects</div>
            <div className="grid-2" style={{ gap: 6 }}>
              {[
                'Exact & near-duplicate rows',
                'Comma / whitespace in amounts',
                'Zero and negative (refund) amounts',
                'Multiple date formats + year-less dates',
                'Ambiguous DD/MM vs MM/DD dates',
                'Missing currency → defaults to INR',
                'Missing payer field',
                'Name variants & case errors',
                'Non-member names in split',
                'Members split after departure',
                'Percentages that don\'t sum to 100%',
                'Settlement rows disguised as expenses',
                'split_type ↔ split_details conflicts',
                '…and more (all flagged, none silent)',
              ].map(item => (
                <div key={item} className="text-sm flex-gap">
                  <span>✓</span><span>{item}</span>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <div className="anomaly-error mb-2">
              <strong>Error:</strong> {error}
            </div>
          )}

          <button className="btn btn-primary" style={{ width: '100%' }}
            type="submit" disabled={loading || !file}>
            {loading ? 'Analysing CSV…' : 'Upload & Analyse'}
          </button>
        </form>
      </div>
    </div>
  );
}
