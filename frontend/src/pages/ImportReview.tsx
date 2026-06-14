import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { importApi } from '../api';
import { ImportRow, ImportReport, Anomaly } from '../types';

const SEVERITY_CLASS: Record<string, string> = {
  info: 'anomaly-info',
  warning: 'anomaly-warning',
  error: 'anomaly-error',
};

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  clean:        { label: '✓ Clean',        cls: 'badge-green'  },
  auto_fixed:   { label: '⚡ Auto-fixed',  cls: 'badge-blue'   },
  needs_review: { label: '⚠ Needs review', cls: 'badge-yellow' },
  rejected:     { label: '✕ Rejected',     cls: 'badge-red'    },
  approved:     { label: '✓ Approved',     cls: 'badge-green'  },
};

const displayValue = (value: unknown): string | undefined => {
  if (value === undefined || value === null) return undefined;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
};

function AnomalyChip({ a }: { a: Anomaly }) {
  return (
    <div className={SEVERITY_CLASS[a.severity] || 'anomaly-info'}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <strong>{a.type}</strong>
        <span className={`badge ${
          a.severity === 'error' ? 'badge-red' :
          a.severity === 'warning' ? 'badge-yellow' : 'badge-blue'
        }`}>{a.severity}</span>
      </div>
      <div style={{ marginTop: 4 }}>{a.message}</div>
      {a.default_action && (
        <div className="text-muted" style={{ marginTop: 4, fontSize: 11 }}>
          Default action: <strong>{a.default_action}</strong>
        </div>
      )}
    </div>
  );
}

function RowCard({
  row,
  onApprove,
  onReject,
  busy,
  readOnly,
}: {
  row: ImportRow;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  busy: boolean;
  readOnly: boolean;
}) {
  const [expanded, setExpanded] = useState(row.status === 'needs_review');
  const info = STATUS_LABELS[row.status] || { label: row.status, cls: 'badge-gray' };
  const parsed = row.parsed_data as Record<string, unknown>;
  const description = displayValue(parsed.description) || row.raw_data.description || '(no description)';
  const date = displayValue(parsed.date) || row.raw_data.date;
  const amount = displayValue(parsed.amount) || row.raw_data.amount;
  const currency = displayValue(parsed.currency) || row.raw_data.currency || 'INR';
  const paidBy = displayValue(parsed.paid_by);
  const splitType = displayValue(parsed.split_type);
  const isSettlement = Boolean(parsed.is_settlement);

  return (
    <div className={`import-row-card status-${row.status}`}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 40, color: 'var(--muted)', fontSize: 12, paddingTop: 2 }}>
          #{row.row_number}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontWeight: 600 }}>
              {description}
            </div>
            <span className={`badge ${info.cls}`}>{info.label}</span>
          </div>

          <div className="flex-gap text-sm text-muted mt-1" style={{ flexWrap: 'wrap', gap: 12 }}>
            <span>📅 {date}</span>
            <span>💰 {amount} {currency}</span>
            {paidBy && <span>👤 Paid by: {paidBy}</span>}
            {splitType && <span>🔀 {splitType}</span>}
            {isSettlement && <span className="badge badge-purple">settlement</span>}
          </div>

          {row.anomalies.length > 0 && (
            <button
              className="btn btn-outline btn-sm mt-1"
              onClick={() => setExpanded(x => !x)}
            >
              {expanded ? '▲ Hide' : '▼ Show'} {row.anomalies.length} anomal{row.anomalies.length === 1 ? 'y' : 'ies'}
            </button>
          )}

          {expanded && (
            <div style={{ marginTop: 8 }}>
              {row.anomalies.map((a, i) => <AnomalyChip key={i} a={a} />)}

              {/* Raw vs parsed diff */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                <div>
                  <div className="text-sm text-muted mb-1"><strong>Original CSV row</strong></div>
                  <pre style={{
                    background: 'var(--bg)', border: '1px solid var(--border)',
                    borderRadius: 6, padding: 8, fontSize: 11, overflow: 'auto', maxHeight: 160,
                  }}>
                    {JSON.stringify(row.raw_data, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="text-sm text-muted mb-1"><strong>After auto-fixes</strong></div>
                  <pre style={{
                    background: '#f0fdf4', border: '1px solid #86efac',
                    borderRadius: 6, padding: 8, fontSize: 11, overflow: 'auto', maxHeight: 160,
                  }}>
                    {JSON.stringify(row.parsed_data, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* Action buttons for non-final rows */}
          {!readOnly && (row.status === 'needs_review' || row.status === 'auto_fixed' || row.status === 'clean') && (
            <div className="flex-gap mt-1">
              <button
                className="btn btn-success btn-sm"
                onClick={() => onApprove(row.id)}
                disabled={busy}
              >✓ Approve</button>
              <button
                className="btn btn-danger btn-sm"
                onClick={() => onReject(row.id)}
                disabled={busy}
              >✕ Reject</button>
            </div>
          )}

          {!readOnly && row.status === 'approved' && (
            <div className="flex-gap mt-1">
              <span className="text-green text-sm">✓ Approved for import</span>
              <button className="btn btn-outline btn-sm" onClick={() => onReject(row.id)} disabled={busy}>
                Undo
              </button>
            </div>
          )}

          {!readOnly && row.status === 'rejected' && (
            <div className="flex-gap mt-1">
              <span className="text-red text-sm">✕ Will be skipped</span>
              <button className="btn btn-outline btn-sm" onClick={() => onApprove(row.id)} disabled={busy}>
                Undo
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ImportReview() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const sid = Number(sessionId);
  const navigate = useNavigate();

  const [rows, setRows] = useState<ImportRow[]>([]);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [sessionStatus, setSessionStatus] = useState('pending');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [commitResult, setCommitResult] = useState<{ imported: number; skipped: number; settlements_created: number } | null>(null);

  const load = async () => {
    const r = await importApi.getRows(sid);
    setRows(r.data.rows);
    setReport(r.data.report);
    setSessionStatus(r.data.status);
    setLoading(false);
  };

  useEffect(() => { load(); }, [sid]);

  const updateRow = async (rowId: number, status: string) => {
    setBusy(true);
    await importApi.updateRow(sid, rowId, status);
    await load();
    setBusy(false);
  };

  const approveAll = async () => {
    setBusy(true);
    const toApprove = rows.filter(r =>
      r.status === 'needs_review' || r.status === 'auto_fixed' || r.status === 'clean'
    );
    for (const r of toApprove) {
      await importApi.updateRow(sid, r.id, 'approved');
    }
    await load();
    setBusy(false);
  };

  const commit = async () => {
    if (!confirm('Commit import? This will write all approved rows to the database.')) return;
    setCommitting(true);
    try {
      const r = await importApi.commit(sid);
      setCommitResult(r.data);
      await load();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Commit failed');
    } finally {
      setCommitting(false);
    }
  };

  const cancel = async () => {
    if (!confirm('Cancel this import? No data will be saved.')) return;
    await importApi.cancel(sid);
    navigate(-1);
  };

  const downloadReport = async () => {
    const response = await importApi.downloadReport(sid);
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `import-report-${sid}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading || !report) return <div className="spinner" />;

  const pendingReview = rows.filter(r => r.status === 'needs_review').length;
  const approved = rows.filter(r => r.status === 'approved' || r.status === 'auto_fixed' || r.status === 'clean').length;

  const filtered = filter === 'all' ? rows
    : filter === 'review' ? rows.filter(r => r.status === 'needs_review')
    : filter === 'anomaly' ? rows.filter(r => r.anomalies.length > 0)
    : filter === 'clean' ? rows.filter(r => r.status === 'clean' || r.status === 'auto_fixed')
    : rows.filter(r => r.status === filter);

  return (
    <div className="page">
      <div className="flex-between mb-2">
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>Import Review</h1>
          <p className="text-sm text-muted">Session #{sid} · Status: <strong>{sessionStatus}</strong></p>
        </div>
        {sessionStatus === 'pending' && (
          <div className="flex-gap">
            <button className="btn btn-outline" onClick={downloadReport}>Download report</button>
            <button className="btn btn-outline" onClick={cancel} disabled={committing}>Cancel import</button>
            {pendingReview === 0 && (
              <button className="btn btn-primary" onClick={commit} disabled={committing}>
                {committing ? 'Committing…' : `Commit ${approved} rows`}
              </button>
            )}
          </div>
        )}
        {sessionStatus !== 'pending' && (
          <button className="btn btn-outline" onClick={downloadReport}>Download report</button>
        )}
      </div>

      {/* Commit result */}
      {commitResult && (
        <div className="card mb-2" style={{ borderLeft: '4px solid var(--success)' }}>
          <div style={{ fontWeight: 700, color: 'var(--success)', fontSize: 16 }}>✓ Import committed</div>
          <div className="flex-gap mt-1">
            <span className="badge badge-green">{commitResult.imported} expenses imported</span>
            <span className="badge badge-purple">{commitResult.settlements_created} settlements created</span>
            <span className="badge badge-gray">{commitResult.skipped} rows skipped</span>
          </div>
        </div>
      )}

      {/* Report summary */}
      <div className="card mb-2">
        <div className="card-title">📋 Import Report — Anomaly Summary</div>
        <div className="grid-3" style={{ marginBottom: 16 }}>
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ fontSize: 28, fontWeight: 800 }}>{report.total_rows}</div>
            <div className="text-muted text-sm">Total rows</div>
          </div>
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--success)' }}>
              {report.clean + report.auto_fixed}
            </div>
            <div className="text-muted text-sm">Auto-processable</div>
          </div>
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--warning)' }}>
              {report.needs_review}
            </div>
            <div className="text-muted text-sm">Need your decision</div>
          </div>
        </div>

        {Object.keys(report.anomaly_counts).length > 0 && (
          <>
            <div className="text-sm text-muted mb-1"><strong>Anomaly types detected:</strong></div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {Object.entries(report.anomaly_counts).map(([type, count]) => (
                <span key={type} className="badge badge-yellow">
                  {type} × {count}
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Action bar */}
      {sessionStatus === 'pending' && (
        <div className="card mb-2" style={{ padding: '12px 16px' }}>
          <div className="flex-between">
            <div className="flex-gap">
              {(['all', 'needs_review', 'auto_fixed', 'clean', 'approved', 'rejected'] as const).map(f => (
                <button
                  key={f}
                  className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-outline'}`}
                  onClick={() => setFilter(f)}
                >
                  {f === 'all' ? `All (${rows.length})` :
                   f === 'needs_review' ? `⚠ Review (${report.needs_review})` :
                   f === 'auto_fixed' ? `⚡ Fixed (${report.auto_fixed})` :
                   f === 'clean' ? `✓ Clean (${report.clean})` :
                   f === 'approved' ? `✓ Approved (${report.approved})` :
                   `✕ Rejected (${report.rejected})`}
                </button>
              ))}
            </div>
            {pendingReview > 0 && (
              <button className="btn btn-warning btn-sm" onClick={approveAll} disabled={busy}>
                Approve all remaining ({pendingReview})
              </button>
            )}
          </div>

          {pendingReview > 0 && (
            <div className="anomaly-warning mt-1" style={{ marginBottom: 0 }}>
              <strong>{pendingReview} row{pendingReview !== 1 ? 's' : ''} need your decision</strong> before you can commit.
              Review each one below, then click "Approve" or "Reject".
            </div>
          )}
        </div>
      )}

      {/* Row list */}
      <div>
        {filtered.map(row => (
          <RowCard
            key={row.id}
            row={row}
            onApprove={id => updateRow(id, 'approved')}
            onReject={id => updateRow(id, 'rejected')}
            busy={busy}
            readOnly={sessionStatus !== 'pending'}
          />
        ))}
        {filtered.length === 0 && (
          <div className="empty">No rows match this filter.</div>
        )}
      </div>

      {/* Bottom commit */}
      {sessionStatus === 'pending' && pendingReview === 0 && !commitResult && (
        <div style={{ position: 'sticky', bottom: 24, textAlign: 'center', marginTop: 24 }}>
          <button
            className="btn btn-primary"
            style={{ padding: '12px 32px', fontSize: 16, boxShadow: 'var(--shadow-lg)' }}
            onClick={commit}
            disabled={committing}
          >
            {committing ? 'Committing…' : `✓ Commit import (${approved} rows)`}
          </button>
        </div>
      )}
    </div>
  );
}
