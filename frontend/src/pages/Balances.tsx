import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { balancesApi, groupsApi } from '../api';
import { GroupBalances, MemberBreakdown, Group } from '../types';

export default function Balances() {
  const { id } = useParams<{ id: string }>();
  const gid = Number(id);

  const [group, setGroup] = useState<Group | null>(null);
  const [balances, setBalances] = useState<GroupBalances | null>(null);
  const [breakdown, setBreakdown] = useState<MemberBreakdown | null>(null);
  const [selectedUid, setSelectedUid] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([groupsApi.get(gid), balancesApi.group(gid)]).then(([g, b]) => {
      setGroup(g.data);
      setBalances(b.data);
      setLoading(false);
    });
  }, [gid]);

  const loadBreakdown = async (uid: number) => {
    if (selectedUid === uid) { setSelectedUid(null); setBreakdown(null); return; }
    setSelectedUid(uid);
    const r = await balancesApi.member(gid, uid);
    setBreakdown(r.data);
  };

  if (loading || !balances || !group) return <div className="spinner" />;

  const fmt = (n: number) =>
    `₹${Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

  const members = Object.entries(balances.members);

  return (
    <div className="page">
      <div className="mb-2">
        <Link to={`/groups/${gid}`} className="text-muted text-sm">← {group.name}</Link>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>Balances</h1>
        <p className="text-sm text-muted">
          USD → INR rate used: {group.usd_inr_rate}. All amounts in ₹.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid-3 mb-2">
        {members.map(([uid, m]) => {
          const positive = m.net >= 0;
          return (
            <div
              key={uid}
              className="card"
              style={{ cursor: 'pointer', borderLeft: `4px solid ${positive ? 'var(--success)' : 'var(--danger)'}` }}
              onClick={() => loadBreakdown(Number(uid))}
            >
              <div style={{ fontWeight: 700, fontSize: 15 }}>{m.name}</div>
              <div style={{
                fontSize: 22, fontWeight: 800, marginTop: 6,
                color: positive ? 'var(--success)' : 'var(--danger)',
              }}>
                {positive ? '+' : '-'}{fmt(m.net)}
              </div>
              <div className="text-sm text-muted mt-1">
                {positive ? 'is owed money' : 'owes money'}
              </div>
              <div className="text-sm mt-1" style={{ color: 'var(--primary)' }}>
                {selectedUid === Number(uid) ? '▲ Hide breakdown' : '▼ Show breakdown'}
              </div>
            </div>
          );
        })}
      </div>

      {/* Suggested transactions — Aisha's "one number per person" */}
      <div className="card mb-2">
        <div className="card-title">💸 Who pays whom (minimum transactions)</div>
        {balances.transactions.length === 0 ? (
          <p className="text-muted">All settled up! 🎉</p>
        ) : (
          <div>
            {balances.transactions.map((t, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 0', borderBottom: i < balances.transactions.length - 1
                  ? '1px solid var(--border)' : 'none',
              }}>
                <span className="badge badge-red">{t.from}</span>
                <span className="text-muted">pays</span>
                <span style={{ fontWeight: 800, fontSize: 16 }}>{fmt(t.amount)}</span>
                <span className="text-muted">to</span>
                <span className="badge badge-green">{t.to}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-member breakdown — Rohan's "no magic numbers" */}
      {selectedUid !== null && breakdown && (
        <div className="card">
          <div className="card-title">
            🔍 Breakdown for {balances.members[selectedUid]?.name}
            <span style={{ marginLeft: 12, fontWeight: 400, color: 'var(--muted)', fontSize: 13 }}>
              Net: <strong style={{ color: breakdown.net >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                {breakdown.net >= 0 ? '+' : ''}{fmt(breakdown.net)}
              </strong>
            </span>
          </div>
          <p className="text-sm text-muted mb-2">
            Every expense that affects this balance. Positive net_effect = this person
            comes out ahead on that row.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Total (₹)</th>
                  <th>I paid</th>
                  <th>My share</th>
                  <th style={{ color: 'var(--primary)' }}>Net effect</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.breakdown.map(row => (
                  <tr key={row.expense_id}>
                    <td className="text-sm text-muted">{row.date}</td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{row.description}</div>
                      {row.currency === 'USD' && (
                        <div className="text-sm text-muted">
                          ${row.original_amount} USD
                        </div>
                      )}
                    </td>
                    <td>{fmt(row.amount_inr)}</td>
                    <td className="text-green">{row.i_paid_inr > 0 ? fmt(row.i_paid_inr) : '—'}</td>
                    <td className="text-red">{row.my_share_inr > 0 ? fmt(row.my_share_inr) : '—'}</td>
                    <td style={{
                      fontWeight: 700,
                      color: row.net_effect >= 0 ? 'var(--success)' : 'var(--danger)',
                    }}>
                      {row.net_effect >= 0 ? '+' : ''}{fmt(row.net_effect)}
                    </td>
                  </tr>
                ))}
                <tr style={{ background: 'var(--bg)' }}>
                  <td colSpan={5} style={{ fontWeight: 700, textAlign: 'right' }}>Total</td>
                  <td style={{
                    fontWeight: 800, fontSize: 16,
                    color: breakdown.net >= 0 ? 'var(--success)' : 'var(--danger)',
                  }}>
                    {breakdown.net >= 0 ? '+' : ''}{fmt(breakdown.net)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
