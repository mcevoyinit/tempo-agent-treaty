import { useState } from 'react';

interface SimResult {
  entity_id: string;
  total_actions: number;
  actions: Array<{
    decision: string;
    field_path: string;
    original_value: string;
    counter_value: string | null;
    reasoning: string;
    confidence: number;
  }>;
  field_statuses: Record<string, string>;
  savings_vs_dex: {
    dex_mid_price: string;
    dex_slippage_bps: number;
    otc_price: string;
    quantity: number;
    seller_savings: string;
    buyer_savings: string;
  } | null;
}

interface MarketData {
  dex_mid_price: string;
  dex_slippage_bps: number;
  liquidity_depth: string;
  seller_effective_dex_price: string;
  buyer_effective_dex_price: string;
  block_quantity: number;
}

const decisionColors: Record<string, string> = {
  ACCEPT: '#22c55e',
  REJECT: '#ef4444',
  COUNTER: '#f59e0b',
  REFER_TO_LLM: '#8b5cf6',
  AWAIT_HUMAN: '#64748b',
};

export function AgentControlPage() {
  const [simResult, setSimResult] = useState<SimResult | null>(null);
  const [market, setMarket] = useState<MarketData | null>(null);
  const [running, setRunning] = useState(false);
  const [quantity, setQuantity] = useState(100000);
  const [price, setPrice] = useState(1.05);

  const runSimulation = async () => {
    setRunning(true);
    try {
      const r = await fetch('/api/agent/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seller_values: {
            price_per_token: String(price),
            quantity: String(quantity),
            min_fill_quantity: String(Math.floor(quantity * 0.5)),
            partial_fill_allowed: 'true',
            settlement_window_secs: '120',
            execution_tranches: '1',
            max_slippage_bps: '50',
            escrow_pct: '50.0',
            penalty_bps: '200',
            expire_after_secs: '600',
            price_oracle_source: 'uniswap_v3',
            twap_window_mins: '30',
          },
        }),
      });
      if (r.ok) setSimResult(await r.json());
    } finally {
      setRunning(false);
    }
  };

  const fetchMarket = async () => {
    const r = await fetch(`/api/agent/market?quantity=${quantity}`);
    if (r.ok) setMarket(await r.json());
  };

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '24px' }}>
        Agent Control Panel
      </h1>

      {/* Controls Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <div style={cardStyle}>
          <label style={labelStyle}>Block Size (tokens)</label>
          <input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
            style={inputStyle}
          />
        </div>
        <div style={cardStyle}>
          <label style={labelStyle}>Seller's Opening Price</label>
          <input
            type="number"
            step="0.01"
            value={price}
            onChange={(e) => setPrice(Number(e.target.value))}
            style={inputStyle}
          />
        </div>
        <div style={{ ...cardStyle, display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button onClick={runSimulation} disabled={running} style={primaryBtn}>
            {running ? 'Negotiating...' : 'Run Dual-Agent Simulation'}
          </button>
          <button onClick={fetchMarket} style={secondaryBtn}>
            Fetch DEX Market Data
          </button>
        </div>
      </div>

      {/* Market Data */}
      {market && (
        <div style={{ ...cardStyle, marginBottom: '24px' }}>
          <h3 style={sectionTitle}>DEX Market Snapshot (BATNA)</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '16px' }}>
            <Stat label="Mid Price" value={`$${market.dex_mid_price}`} />
            <Stat label="Slippage" value={`${market.dex_slippage_bps} bps`} warn={market.dex_slippage_bps > 100} />
            <Stat label="Liquidity" value={`$${Number(market.liquidity_depth).toLocaleString()}`} />
            <Stat label="Seller Effective" value={`$${Number(market.seller_effective_dex_price).toFixed(4)}`} />
            <Stat label="Buyer Effective" value={`$${Number(market.buyer_effective_dex_price).toFixed(4)}`} />
          </div>
        </div>
      )}

      {/* Savings Card */}
      {simResult?.savings_vs_dex && (
        <div style={{ ...cardStyle, marginBottom: '24px', border: '1px solid #22c55e44' }}>
          <h3 style={sectionTitle}>OTC vs DEX Savings</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
            <Stat label="OTC Price" value={`$${simResult.savings_vs_dex.otc_price}`} />
            <Stat label="DEX Mid" value={`$${simResult.savings_vs_dex.dex_mid_price}`} />
            <Stat
              label="Seller Saves"
              value={`$${Number(simResult.savings_vs_dex.seller_savings).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              good
            />
            <Stat
              label="Buyer Saves"
              value={`$${Number(simResult.savings_vs_dex.buyer_savings).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
              good
            />
          </div>
        </div>
      )}

      {/* Simulation Results */}
      {simResult && (
        <>
          {/* Field Status Summary */}
          <div style={{ ...cardStyle, marginBottom: '24px' }}>
            <h3 style={sectionTitle}>
              Final Field Statuses —{' '}
              <span style={{ color: '#22c55e' }}>
                {Object.values(simResult.field_statuses).filter((s) => s === 'AGREED').length}/12 Agreed
              </span>
            </h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {Object.entries(simResult.field_statuses).map(([field, status]) => (
                <span
                  key={field}
                  style={{
                    padding: '4px 12px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: 600,
                    background: status === 'AGREED' ? '#052e16' : '#312e81',
                    color: status === 'AGREED' ? '#4ade80' : '#a5b4fc',
                  }}
                >
                  {field}: {status}
                </span>
              ))}
            </div>
          </div>

          {/* Decision Log */}
          <div style={cardStyle}>
            <h3 style={sectionTitle}>
              Agent Decision Log ({simResult.total_actions} actions)
            </h3>
            <div style={{ maxHeight: '400px', overflow: 'auto' }}>
              {simResult.actions.map((a, i) => (
                <div key={i} style={logRow}>
                  <span style={{ width: '24px', color: '#64748b', fontSize: '12px' }}>
                    {i + 1}
                  </span>
                  <span
                    style={{
                      width: '80px',
                      fontSize: '11px',
                      fontWeight: 700,
                      color: decisionColors[a.decision] || '#94a3b8',
                    }}
                  >
                    {a.decision}
                  </span>
                  <code style={{ width: '180px', fontSize: '12px', color: '#818cf8' }}>
                    {a.field_path}
                  </code>
                  <span style={{ flex: 1, fontSize: '12px', color: '#94a3b8' }}>
                    {a.reasoning}
                  </span>
                  {a.counter_value && (
                    <span style={{ fontSize: '12px', color: '#fbbf24' }}>
                      &rarr; {a.counter_value}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  warn,
  good,
}: {
  label: string;
  value: string;
  warn?: boolean;
  good?: boolean;
}) {
  return (
    <div>
      <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div
        style={{
          fontSize: '20px',
          fontWeight: 700,
          color: warn ? '#f59e0b' : good ? '#22c55e' : '#f8fafc',
        }}
      >
        {value}
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: '#1e293b',
  borderRadius: '12px',
  padding: '20px',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '12px',
  fontWeight: 600,
  color: '#64748b',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: '8px',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  background: '#0f172a',
  border: '1px solid #334155',
  borderRadius: '8px',
  color: '#f8fafc',
  fontSize: '16px',
  fontWeight: 600,
};

const primaryBtn: React.CSSProperties = {
  background: '#6366f1',
  color: '#fff',
  border: 'none',
  padding: '12px',
  borderRadius: '8px',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '14px',
};

const secondaryBtn: React.CSSProperties = {
  background: 'transparent',
  color: '#818cf8',
  border: '1px solid #334155',
  padding: '10px',
  borderRadius: '8px',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '13px',
};

const sectionTitle: React.CSSProperties = {
  fontSize: '14px',
  fontWeight: 700,
  marginBottom: '16px',
};

const logRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  padding: '6px 0',
  borderBottom: '1px solid #0f172a',
};
