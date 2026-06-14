import { useState, useEffect, FormEvent } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { groupsApi, expensesApi, settlementsApi } from '../api';
import { Group, Expense, Settlement, GroupMember } from '../types';
import { useAuth } from '../context/AuthContext';

type Tab = 'expenses' | 'members' | 'settlements';

const SPLIT_TYPES = ['equal', 'unequal', 'percentage', 'share'];
const CURRENCIES = ['INR', 'USD'];

export default function GroupDetail() {
  const { id } = useParams<{ id: string }>();
  const gid = Number(id);
  const { user } = useAuth();
  const navigate = useNavigate();

  const [group, setGroup] = useState<Group | null>(null);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [tab, setTab] = useState<Tab>('expenses');
  const [loading, setLoading] = useState(true);

  // Expense form
  const [showExpForm, setShowExpForm] = useState(false);
  const [expDesc, setExpDesc] = useState('');
  const [expAmount, setExpAmount] = useState('');
  const [expCurrency, setExpCurrency] = useState('INR');
  const [expDate, setExpDate] = useState(new Date().toISOString().split('T')[0]);
  const [expPaidBy, setExpPaidBy] = useState('');
  const [expSplitType, setExpSplitType] = useState('equal');
  const [expSplitMembers, setExpSplitMembers] = useState<string[]>([]);
  const [expSplitValues, setExpSplitValues] = useState<Record<string, string>>({});
  const [expNotes, setExpNotes] = useState('');
  const [expError, setExpError] = useState('');
  const [expLoading, setExpLoading] = useState(false);

  // Settlement form
  const [showSettleForm, setShowSettleForm] = useState(false);
  const [stlPayer, setStlPayer] = useState('');
  const [stlReceiver, setStlReceiver] = useState('');
  const [stlAmount, setStlAmount] = useState('');
  const [stlDate, setStlDate] = useState(new Date().toISOString().split('T')[0]);
  const [stlNotes, setStlNotes] = useState('');
  const [stlError, setStlError] = useState('');

  // Add member form
  const [showMemberForm, setShowMemberForm] = useState(false);
  const [memberEmail, setMemberEmail] = useState('');
  const [memberJoined, setMemberJoined] = useState('');
  const [memberError, setMemberError] = useState('');

  const load = async () => {
    const [g, e, s] = await Promise.all([
      groupsApi.get(gid),
      expensesApi.list(gid),
      settlementsApi.list(gid),
    ]);
    setGroup(g.data);
    setExpenses(e.data);
    setSettlements(s.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, [gid]);

  useEffect(() => {
    if (group) {
      const activeIds = group.members.filter(m => m.active).map(m => String(m.user_id));
      setExpSplitMembers(activeIds);
      setExpPaidBy(String(user?.id || activeIds[0] || ''));
    }
  }, [group]);

  const activeMembers = group?.members.filter(m => m.active) || [];
  const memberActiveOn = (m: GroupMember, value: string) =>
    (!m.joined_at || m.joined_at <= value) && (!m.left_at || m.left_at >= value);

  const buildSplitArg = (): string => {
    if (expSplitType === 'equal') {
      const obj: Record<string, number> = {};
      expSplitMembers.forEach(uid => { obj[uid] = 1; });
      return JSON.stringify(obj);
    }
    const obj: Record<string, number> = {};
    expSplitMembers.forEach(uid => { obj[uid] = parseFloat(expSplitValues[uid] || '0'); });
    return JSON.stringify(obj);
  };

  const submitExpense = async (e: FormEvent) => {
    e.preventDefault();
    setExpError(''); setExpLoading(true);
    try {
      const amount = parseFloat(expAmount);
      if (!Number.isFinite(amount)) throw new Error('Enter a valid amount');
      if (!expPaidBy) throw new Error('Choose who paid');
      if (expSplitMembers.length === 0) throw new Error('Choose at least one split member');
      const eligibleIds = new Set(group?.members.filter(m => memberActiveOn(m, expDate)).map(m => String(m.user_id)) || []);
      if (!eligibleIds.has(expPaidBy) || expSplitMembers.some(uid => !eligibleIds.has(uid))) {
        throw new Error('Payer and split members must be active on the expense date');
      }
      if (expSplitType !== 'equal') {
        const values = expSplitMembers.map(uid => parseFloat(expSplitValues[uid] || ''));
        if (values.some(v => !Number.isFinite(v) || v < 0)) {
          throw new Error('Enter non-negative split values for every selected member');
        }
        if ((expSplitType === 'percentage' || expSplitType === 'share') && values.reduce((a, b) => a + b, 0) <= 0) {
          throw new Error('Split total must be greater than zero');
        }
      }
      await expensesApi.create(gid, {
        description: expDesc,
        amount,
        currency: expCurrency,
        paid_by_user_id: parseInt(expPaidBy),
        split_type: expSplitType,
        expense_date: expDate,
        split_members: buildSplitArg(),
        notes: expNotes || undefined,
      });
      setShowExpForm(false);
      setExpDesc(''); setExpAmount(''); setExpNotes('');
      await load();
    } catch (err: any) {
      setExpError(err?.response?.data?.detail || err?.message || 'Failed');
    } finally {
      setExpLoading(false);
    }
  };

  const submitSettlement = async (e: FormEvent) => {
    e.preventDefault();
    setStlError('');
    try {
      if (!stlPayer || !stlReceiver) throw new Error('Choose payer and receiver');
      if (stlPayer === stlReceiver) throw new Error('Payer and receiver must be different');
      const amount = parseFloat(stlAmount);
      if (!Number.isFinite(amount) || amount <= 0) throw new Error('Enter a positive amount');
      const eligibleIds = new Set(group?.members.filter(m => memberActiveOn(m, stlDate)).map(m => String(m.user_id)) || []);
      if (!eligibleIds.has(stlPayer) || !eligibleIds.has(stlReceiver)) {
        throw new Error('Payer and receiver must be active on the settlement date');
      }
      await settlementsApi.create(gid, {
        payer_id: parseInt(stlPayer),
        receiver_id: parseInt(stlReceiver),
        amount,
        currency: 'INR',
        settlement_date: stlDate,
        notes: stlNotes || undefined,
      });
      setShowSettleForm(false);
      setStlPayer(''); setStlReceiver(''); setStlAmount(''); setStlNotes('');
      await load();
    } catch (err: any) {
      setStlError(err?.response?.data?.detail || err?.message || 'Failed');
    }
  };

  const submitMember = async (e: FormEvent) => {
    e.preventDefault();
    setMemberError('');
    try {
      await groupsApi.addMember(gid, memberEmail, memberJoined);
      setShowMemberForm(false);
      setMemberEmail(''); setMemberJoined('');
      await load();
    } catch (err: any) {
      setMemberError(err?.response?.data?.detail || 'Failed');
    }
  };

  const markLeft = async (m: GroupMember) => {
    const d = prompt(`Set departure date for ${m.name} (YYYY-MM-DD):`, new Date().toISOString().split('T')[0]);
    if (!d) return;
    await groupsApi.updateMember(gid, m.user_id, { left_at: d });
    await load();
  };

  const deleteExpense = async (eid: number) => {
    if (!confirm('Delete this expense?')) return;
    await expensesApi.delete(eid);
    await load();
  };

  if (loading || !group) return <div className="spinner" />;

  const fmt = (n: number, cur = 'INR') =>
    cur === 'USD' ? `$${n.toFixed(2)}` : `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
  const expenseMembers = group.members.filter(m => memberActiveOn(m, expDate));
  const settlementMembers = group.members.filter(m => memberActiveOn(m, stlDate));

  return (
    <div className="page">
      <div className="flex-between mb-2">
        <div>
          <Link to="/" className="text-muted text-sm">← Groups</Link>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{group.name}</h1>
          <p className="text-sm text-muted">USD/INR rate: {group.usd_inr_rate}</p>
        </div>
        <div className="flex-gap">
          <Link to={`/groups/${gid}/balances`} className="btn btn-outline">📊 Balances</Link>
          <Link to={`/groups/${gid}/import`} className="btn btn-outline">📂 Import CSV</Link>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex-gap mb-2" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {(['expenses', 'members', 'settlements'] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '10px 16px', fontWeight: tab === t ? 700 : 400,
              color: tab === t ? 'var(--primary)' : 'var(--muted)',
              borderBottom: tab === t ? '2px solid var(--primary)' : '2px solid transparent',
              marginBottom: -1, fontSize: 14,
            }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'expenses' && ` (${expenses.length})`}
            {t === 'settlements' && ` (${settlements.length})`}
          </button>
        ))}
      </div>

      {/* EXPENSES TAB */}
      {tab === 'expenses' && (
        <>
          <div className="flex-between mb-2">
            <span className="text-muted text-sm">{expenses.length} expenses</span>
            <button className="btn btn-primary" onClick={() => setShowExpForm(true)}>+ Add Expense</button>
          </div>

          {expenses.length === 0 ? (
            <div className="empty">No expenses yet.</div>
          ) : (
            <div className="card" style={{ padding: 0 }}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th><th>Description</th><th>Paid by</th>
                      <th>Amount</th><th>Split</th><th>Split among</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {expenses.map(e => (
                      <tr key={e.id}>
                        <td className="text-sm text-muted">{e.expense_date}</td>
                        <td>
                          <div style={{ fontWeight: 500 }}>{e.description}</div>
                          {e.notes && <div className="text-sm text-muted">{e.notes}</div>}
                          {e.import_session_id && <span className="badge badge-blue text-sm">imported</span>}
                        </td>
                        <td>{e.paid_by_name || '—'}</td>
                        <td className="font-bold">
                          {fmt(e.amount, e.currency)}
                          {e.currency === 'USD' && (
                            <div className="text-sm text-muted">
                              ≈ {fmt(e.amount * (group.usd_inr_rate))}
                            </div>
                          )}
                        </td>
                        <td><span className="badge badge-purple">{e.split_type}</span></td>
                        <td>
                          {e.splits.map(s => (
                            <div key={s.user_id} className="text-sm">
                              {s.name}: {fmt(s.amount_inr)}
                            </div>
                          ))}
                        </td>
                        <td>
                          <button className="btn btn-danger btn-sm"
                            onClick={() => deleteExpense(e.id)}>✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* MEMBERS TAB */}
      {tab === 'members' && (
        <>
          <div className="flex-between mb-2">
            <span className="text-muted text-sm">{group.members.length} total members</span>
            <button className="btn btn-primary" onClick={() => setShowMemberForm(true)}>+ Add Member</button>
          </div>
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr><th>Name</th><th>Email</th><th>Joined</th><th>Left</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {group.members.map(m => (
                  <tr key={m.user_id}>
                    <td style={{ fontWeight: 500 }}>{m.name}</td>
                    <td className="text-muted">{m.email}</td>
                    <td>{m.joined_at}</td>
                    <td>{m.left_at || '—'}</td>
                    <td>
                      <span className={`badge ${m.active ? 'badge-green' : 'badge-gray'}`}>
                        {m.active ? 'Active' : 'Left'}
                      </span>
                    </td>
                    <td>
                      {m.active && (
                        <button className="btn btn-outline btn-sm" onClick={() => markLeft(m)}>
                          Mark departed
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* SETTLEMENTS TAB */}
      {tab === 'settlements' && (
        <>
          <div className="flex-between mb-2">
            <span className="text-muted text-sm">{settlements.length} settlements</span>
            <button className="btn btn-primary" onClick={() => setShowSettleForm(true)}>+ Record Payment</button>
          </div>
          {settlements.length === 0 ? (
            <div className="empty">No settlements yet.</div>
          ) : (
            <div className="card" style={{ padding: 0 }}>
              <table>
                <thead><tr><th>Date</th><th>From</th><th>To</th><th>Amount</th><th>Notes</th></tr></thead>
                <tbody>
                  {settlements.map(s => (
                    <tr key={s.id}>
                      <td>{s.settlement_date}</td>
                      <td style={{ fontWeight: 500 }}>{s.payer_name}</td>
                      <td>{s.receiver_name}</td>
                      <td className="font-bold">{fmt(s.amount, s.currency)}</td>
                      <td className="text-muted">{s.notes || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ADD EXPENSE MODAL */}
      {showExpForm && (
        <div className="modal-overlay" onClick={() => setShowExpForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Add Expense</div>
            <form onSubmit={submitExpense}>
              <div className="form-group">
                <label>Description</label>
                <input className="input" value={expDesc} onChange={e => setExpDesc(e.target.value)} required />
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label>Amount</label>
                  <input className="input" type="number" step="0.01" value={expAmount}
                    onChange={e => setExpAmount(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>Currency</label>
                  <select className="input" value={expCurrency} onChange={e => setExpCurrency(e.target.value)}>
                    {CURRENCIES.map(c => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label>Date</label>
                  <input className="input" type="date" value={expDate}
                    onChange={e => setExpDate(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>Paid by</label>
                  <select className="input" value={expPaidBy} onChange={e => setExpPaidBy(e.target.value)} required>
                    {expenseMembers.map(m => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>Split type</label>
                <select className="input" value={expSplitType} onChange={e => setExpSplitType(e.target.value)}>
                  {SPLIT_TYPES.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Split among</label>
                <div className="flex-gap" style={{ flexWrap: 'wrap' }}>
                  {expenseMembers.map(m => {
                    const uid = String(m.user_id);
                    const checked = expSplitMembers.includes(uid);
                    return (
                      <label key={uid} className="flex-gap" style={{ cursor: 'pointer' }}>
                        <input type="checkbox" checked={checked}
                          onChange={() => {
                            setExpSplitMembers(prev =>
                              checked ? prev.filter(x => x !== uid) : [...prev, uid]
                            );
                          }} />
                        {m.name}
                        {expSplitType !== 'equal' && checked && (
                          <input
                            className="input input-sm"
                            style={{ width: 70 }}
                            placeholder={expSplitType === 'percentage' ? '%' : expSplitType === 'share' ? 'share' : '₹'}
                            value={expSplitValues[uid] || ''}
                            onChange={ev => setExpSplitValues(p => ({ ...p, [uid]: ev.target.value }))}
                          />
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="form-group">
                <label>Notes (optional)</label>
                <input className="input" value={expNotes} onChange={e => setExpNotes(e.target.value)} />
              </div>
              {expError && <p className="text-red text-sm mb-1">{expError}</p>}
              <div className="flex-gap" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowExpForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={expLoading}>
                  {expLoading ? 'Saving…' : 'Add Expense'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* RECORD PAYMENT MODAL */}
      {showSettleForm && (
        <div className="modal-overlay" onClick={() => setShowSettleForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Record Payment</div>
            <form onSubmit={submitSettlement}>
              <div className="form-group">
                <label>Who paid?</label>
                <select className="input" value={stlPayer} onChange={e => setStlPayer(e.target.value)} required>
                  <option value="">— select —</option>
                  {settlementMembers.map(m => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>Paid to</label>
                <select className="input" value={stlReceiver} onChange={e => setStlReceiver(e.target.value)} required>
                  <option value="">— select —</option>
                  {settlementMembers.map(m => <option key={m.user_id} value={m.user_id}>{m.name}</option>)}
                </select>
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label>Amount (₹)</label>
                  <input className="input" type="number" step="0.01" value={stlAmount}
                    onChange={e => setStlAmount(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>Date</label>
                  <input className="input" type="date" value={stlDate}
                    onChange={e => setStlDate(e.target.value)} required />
                </div>
              </div>
              <div className="form-group">
                <label>Notes</label>
                <input className="input" value={stlNotes} onChange={e => setStlNotes(e.target.value)} />
              </div>
              {stlError && <p className="text-red text-sm mb-1">{stlError}</p>}
              <div className="flex-gap" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowSettleForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-success">Record Payment</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ADD MEMBER MODAL */}
      {showMemberForm && (
        <div className="modal-overlay" onClick={() => setShowMemberForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Add Member</div>
            <p className="text-sm text-muted mb-2">
              The user must already have an account. Use their registered email.
            </p>
            <form onSubmit={submitMember}>
              <div className="form-group">
                <label>Email address</label>
                <input className="input" type="email" value={memberEmail}
                  onChange={e => setMemberEmail(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Joined date</label>
                <input className="input" type="date" value={memberJoined}
                  onChange={e => setMemberJoined(e.target.value)} required />
              </div>
              {memberError && <p className="text-red text-sm mb-1">{memberError}</p>}
              <div className="flex-gap" style={{ justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline" onClick={() => setShowMemberForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Add</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
