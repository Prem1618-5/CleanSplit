import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { groupsApi } from '../api';
import { Group } from '../types';

export default function Dashboard() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newRate, setNewRate] = useState('85');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const r = await groupsApi.list();
      setGroups(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await groupsApi.create(newName, parseFloat(newRate));
      setNewName(''); setNewRate('85'); setCreating(false);
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed');
    }
  };

  if (loading) return <div className="spinner" />;

  return (
    <div className="page">
      <div className="flex-between mb-2">
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Your Groups</h1>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + New Group
        </button>
      </div>

      {creating && (
        <div className="modal-overlay" onClick={() => setCreating(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Create Group</div>
            <form onSubmit={create}>
              <div className="form-group">
                <label>Group name</label>
                <input className="input" value={newName} onChange={e => setNewName(e.target.value)}
                  required placeholder="Flat 4B" autoFocus />
              </div>
              <div className="form-group">
                <label>USD → INR rate (for currency conversion)</label>
                <input className="input" type="number" step="0.01" value={newRate}
                  onChange={e => setNewRate(e.target.value)} required />
                <p className="text-sm text-muted mt-1">
                  Used when converting USD expenses. Can be changed later.
                </p>
              </div>
              {error && <p className="text-red text-sm mb-1">{error}</p>}
              <div className="flex-gap" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline"
                  onClick={() => setCreating(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {groups.length === 0 ? (
        <div className="empty">
          <p>No groups yet.</p>
          <p className="text-sm mt-1">Create one to start tracking expenses.</p>
        </div>
      ) : (
        <div className="grid-2">
          {groups.map(g => (
            <Link key={g.id} to={`/groups/${g.id}`} style={{ textDecoration: 'none' }}>
              <div className="card" style={{ cursor: 'pointer', transition: 'box-shadow .15s' }}
                onMouseEnter={e => (e.currentTarget.style.boxShadow = 'var(--shadow-lg)')}
                onMouseLeave={e => (e.currentTarget.style.boxShadow = 'var(--shadow)')}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>🏠</div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{g.name}</div>
                <div className="text-muted text-sm mt-1">
                  {g.members.length} member{g.members.length !== 1 ? 's' : ''} ·{' '}
                  ₹1 = ${(1 / g.usd_inr_rate).toFixed(4)}
                </div>
                <div className="flex-gap mt-2" style={{ flexWrap: 'wrap' }}>
                  {g.members.map(m => (
                    <span key={m.user_id}
                      className={`badge ${m.active ? 'badge-green' : 'badge-gray'}`}>
                      {m.name}
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
