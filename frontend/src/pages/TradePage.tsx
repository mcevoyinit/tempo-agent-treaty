import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { otcBlockTradeConfig } from '../config/otc-entity-config';

interface FieldStatuses {
  [fieldPath: string]: string;
}

interface Trade {
  id: string;
  status: string;
  seller_id: string;
  buyer_id: string;
  [key: string]: unknown;
}

const statusBadge: Record<string, { bg: string; text: string }> = {
  DRAFT: { bg: '#334155', text: '#94a3b8' },
  PROPOSED: { bg: '#312e81', text: '#a5b4fc' },
  COUNTER_PROPOSED: { bg: '#451a03', text: '#fbbf24' },
  AGREED: { bg: '#052e16', text: '#4ade80' },
  LOCKED: { bg: '#1e293b', text: '#64748b' },
  REJECTED: { bg: '#450a0a', text: '#f87171' },
};

export function TradePage() {
  const { tradeId } = useParams<{ tradeId: string }>();
  const navigate = useNavigate();
  const [trade, setTrade] = useState<Trade | null>(null);
  const [fieldStatuses, setFieldStatuses] = useState<FieldStatuses>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!tradeId) return;
    try {
      const [tradeRes, statusRes] = await Promise.all([
        fetch(`/api/trades/${tradeId}`),
        fetch(`/api/negotiation/entity/${tradeId}/status`),
      ]);
      if (tradeRes.ok) setTrade(await tradeRes.json());
      if (statusRes.ok) {
        const data = await statusRes.json();
        setFieldStatuses(data.field_statuses || {});
      }
    } catch {
      // Backend not running
    } finally {
      setLoading(false);
    }
  }, [tradeId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <p style={{ color: '#94a3b8' }}>Loading...</p>;
  if (!trade) return <p style={{ color: '#ef4444' }}>Trade not found</p>;

  const agreedCount = Object.values(fieldStatuses).filter((s) => s === 'AGREED').length;
  const totalFields = otcBlockTradeConfig.negotiableFields?.length ?? 12;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
        <button onClick={() => navigate('/')} style={backBtn}>&larr;</button>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700 }}>
            <code style={{ color: '#818cf8' }}>{trade.id}</code>
          </h1>
          <span style={{ color: '#64748b', fontSize: '13px' }}>
            {trade.seller_id} &harr; {trade.buyer_id}
          </span>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ProgressRing agreed={agreedCount} total={totalFields} />
        </div>
      </div>

      {/* Negotiation Field Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {otcBlockTradeConfig.sections.map((section) => (
          <div key={section.id} style={sectionCard}>
            <h3 style={{ fontSize: '13px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              {section.title}
            </h3>
            {section.fields.map((fp) => {
              const fieldConfig = otcBlockTradeConfig.fields[fp];
              const status = fieldStatuses[fp] || 'DRAFT';
              const badge = statusBadge[status] || statusBadge.DRAFT;
              return (
                <div key={fp} style={fieldRow}>
                  <span style={{ fontSize: '14px', color: '#e2e8f0' }}>
                    {fieldConfig?.label || fp}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '8px',
                      background: badge.bg,
                      color: badge.text,
                    }}
                  >
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function ProgressRing({ agreed, total }: { agreed: number; total: number }) {
  const pct = total > 0 ? Math.round((agreed / total) * 100) : 0;
  const r = 28;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#334155" strokeWidth="4" />
        <circle
          cx="32" cy="32" r={r} fill="none"
          stroke={pct === 100 ? '#22c55e' : '#6366f1'}
          strokeWidth="4"
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 32 32)"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
        <text x="32" y="36" textAnchor="middle" fill="#f8fafc" fontSize="14" fontWeight="700">
          {pct}%
        </text>
      </svg>
      <div>
        <div style={{ fontSize: '16px', fontWeight: 700 }}>
          {agreed}/{total}
        </div>
        <div style={{ fontSize: '12px', color: '#64748b' }}>fields agreed</div>
      </div>
    </div>
  );
}

const sectionCard: React.CSSProperties = {
  background: '#1e293b',
  borderRadius: '12px',
  padding: '20px',
};

const fieldRow: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '8px 0',
  borderBottom: '1px solid #334155',
};

const backBtn: React.CSSProperties = {
  background: '#334155',
  color: '#f8fafc',
  border: 'none',
  width: '36px',
  height: '36px',
  borderRadius: '8px',
  cursor: 'pointer',
  fontSize: '16px',
};
