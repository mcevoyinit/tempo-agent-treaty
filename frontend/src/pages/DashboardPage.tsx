import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface Trade {
  id: string;
  status: string;
  seller_id: string;
  buyer_id: string;
  price_per_token?: number;
  quantity?: number;
  created_at: string;
}

const statusColors: Record<string, string> = {
  INDICATION: '#f59e0b',
  NEGOTIATION: '#6366f1',
  AGREED: '#22c55e',
  SETTLING: '#3b82f6',
  SETTLED: '#10b981',
  FAILED: '#ef4444',
};

export function DashboardPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchTrades = async () => {
    try {
      const r = await fetch('/api/trades');
      const data = await r.json();
      setTrades(data.trades || []);
    } catch {
      // Backend not running yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 3000);
    return () => clearInterval(interval);
  }, []);

  const createTrade = async () => {
    const r = await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seller_id: 'seller-node',
        buyer_id: 'buyer-node',
        price_per_token: 1.05,
        quantity: 100000,
      }),
    });
    if (r.ok) {
      const trade = await r.json();
      setTrades((prev) => [trade, ...prev]);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700 }}>Trade Blotter</h1>
        <button onClick={createTrade} style={btnStyle}>
          + New IOI
        </button>
      </div>

      {loading ? (
        <p style={{ color: '#94a3b8' }}>Loading...</p>
      ) : trades.length === 0 ? (
        <div style={emptyStyle}>
          <p style={{ fontSize: '18px', marginBottom: '8px' }}>No trades yet</p>
          <p style={{ color: '#64748b' }}>Create an Indication of Interest to start</p>
        </div>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Trade ID</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Price</th>
              <th style={thStyle}>Qty</th>
              <th style={thStyle}>Seller</th>
              <th style={thStyle}>Buyer</th>
              <th style={thStyle}>Created</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr
                key={t.id}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/trade/${t.id}`)}
              >
                <td style={tdStyle}>
                  <code style={{ color: '#818cf8', fontSize: '13px' }}>{t.id}</code>
                </td>
                <td style={tdStyle}>
                  <span
                    style={{
                      ...badgeStyle,
                      background: `${statusColors[t.status] || '#64748b'}22`,
                      color: statusColors[t.status] || '#64748b',
                      borderColor: statusColors[t.status] || '#64748b',
                    }}
                  >
                    {t.status}
                  </span>
                </td>
                <td style={tdStyle}>{t.price_per_token ?? '—'}</td>
                <td style={tdStyle}>{t.quantity?.toLocaleString() ?? '—'}</td>
                <td style={tdStyle}><code style={{ fontSize: '12px', color: '#94a3b8' }}>{t.seller_id}</code></td>
                <td style={tdStyle}><code style={{ fontSize: '12px', color: '#94a3b8' }}>{t.buyer_id}</code></td>
                <td style={tdStyle}><span style={{ fontSize: '12px', color: '#64748b' }}>{new Date(t.created_at).toLocaleTimeString()}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: '#6366f1',
  color: '#fff',
  border: 'none',
  padding: '10px 20px',
  borderRadius: '8px',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '14px',
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  background: '#1e293b',
  borderRadius: '12px',
  overflow: 'hidden',
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '12px 16px',
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  borderBottom: '1px solid #334155',
};

const tdStyle: React.CSSProperties = {
  padding: '12px 16px',
  borderBottom: '1px solid #1e293b',
  fontSize: '14px',
};

const badgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '3px 10px',
  borderRadius: '12px',
  fontSize: '11px',
  fontWeight: 700,
  letterSpacing: '0.03em',
  border: '1px solid',
};

const emptyStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '64px',
  background: '#1e293b',
  borderRadius: '12px',
};
