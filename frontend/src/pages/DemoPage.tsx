import { useState, useEffect, useRef, useCallback } from 'react';

/* ═══════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════ */

interface SimAction {
  agent: 'seller' | 'buyer';
  decision: string;
  field_path: string;
  original_value: string;
  counter_value: string | null;
  reasoning: string;
  confidence: number;
}

interface SimResult {
  entity_id: string;
  total_actions: number;
  actions: SimAction[];
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

type Phase = 'idle' | 'market' | 'negotiating' | 'settling' | 'done';

/* ═══════════════════════════════════════════════════════════════
   Field Metadata — the 12 negotiable fields
   ═══════════════════════════════════════════════════════════════ */

const FIELDS: { key: string; label: string; unit: string; format?: (v: string) => string }[] = [
  { key: 'price_per_token',        label: 'PRICE',       unit: '$/tok',  format: v => `$${v}` },
  { key: 'quantity',               label: 'BLOCK SIZE',  unit: 'tokens', format: v => Number(v).toLocaleString() },
  { key: 'min_fill_quantity',      label: 'MIN FILL',    unit: 'tokens', format: v => Number(v).toLocaleString() },
  { key: 'partial_fill_allowed',   label: 'PARTIAL',     unit: '',       format: v => v === 'true' ? 'YES' : 'NO' },
  { key: 'settlement_window_secs', label: 'SETTLE',      unit: 'sec' },
  { key: 'execution_tranches',     label: 'TRANCHES',    unit: '' },
  { key: 'max_slippage_bps',       label: 'SLIPPAGE',    unit: 'bps' },
  { key: 'escrow_pct',             label: 'ESCROW',      unit: '%',      format: v => `${v}%` },
  { key: 'penalty_bps',            label: 'PENALTY',     unit: 'bps' },
  { key: 'expire_after_secs',      label: 'EXPIRY',      unit: 'sec' },
  { key: 'price_oracle_source',    label: 'ORACLE',      unit: '',       format: v => v.replace('_', ' ').toUpperCase() },
  { key: 'twap_window_mins',       label: 'TWAP',        unit: 'min' },
];

const SELLER_VALUES: Record<string, string> = {
  price_per_token: '1.05', quantity: '100000', min_fill_quantity: '50000',
  partial_fill_allowed: 'true', settlement_window_secs: '120', execution_tranches: '1',
  max_slippage_bps: '50', escrow_pct: '50.0', penalty_bps: '200',
  expire_after_secs: '600', price_oracle_source: 'uniswap_v3', twap_window_mins: '30',
};

/* ═══════════════════════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════════════════════ */

export function DemoPage() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [market, setMarket] = useState<MarketData | null>(null);
  const [result, setResult] = useState<SimResult | null>(null);
  const [fieldStatuses, setFieldStatuses] = useState<Record<string, string>>({});
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [visibleActions, setVisibleActions] = useState<SimAction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [visibleActions]);

  const runDemo = useCallback(async () => {
    setPhase('market');
    setError(null);
    setResult(null);
    setFieldStatuses({});
    setFieldValues({});
    setVisibleActions([]);
    setElapsed(0);

    const t0 = Date.now();
    timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 60);

    try {
      const mRes = await fetch('/api/agent/market?quantity=100000');
      if (!mRes.ok) throw new Error('Backend offline — run: uvicorn backend.app:app --port 8000');
      const mData: MarketData = await mRes.json();
      setMarket(mData);
      await sleep(700);

      setPhase('negotiating');
      const sRes = await fetch('/api/agent/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seller_values: SELLER_VALUES }),
      });
      const sData: SimResult = await sRes.json();
      setResult(sData);

      // Animate each action
      for (let i = 0; i < sData.actions.length; i++) {
        const a = sData.actions[i];
        const delay = a.decision === 'COUNTER' ? 300 : a.reasoning.startsWith('Initiated') ? 60 : 140;
        await sleep(delay);
        setVisibleActions(sData.actions.slice(0, i + 1));

        const fp = a.field_path;
        if (a.decision === 'ACCEPT' && a.reasoning.startsWith('Initiated')) {
          setFieldStatuses(prev => ({ ...prev, [fp]: 'PROPOSED' }));
          setFieldValues(prev => ({ ...prev, [fp]: a.original_value }));
        } else if (a.decision === 'ACCEPT') {
          setFieldStatuses(prev => ({ ...prev, [fp]: 'AGREED' }));
          setFieldValues(prev => ({ ...prev, [fp]: a.original_value }));
        } else if (a.decision === 'COUNTER') {
          setFieldStatuses(prev => ({ ...prev, [fp]: 'COUNTER_PROPOSED' }));
          setFieldValues(prev => ({ ...prev, [fp]: a.counter_value || a.original_value }));
        }
      }

      await sleep(250);
      setFieldStatuses(sData.field_statuses);
      setPhase('settling');
      await sleep(1500);
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setPhase('idle');
    } finally {
      clearInterval(timerRef.current);
    }
  }, []);

  const agreedCount = Object.values(fieldStatuses).filter(s => s === 'AGREED').length;
  const counterCount = visibleActions.filter(a => a.decision === 'COUNTER').length;

  return (
    <div style={{ position: 'relative', minHeight: '100vh' }}>
      {/* Teal spotlight behind header */}
      <div style={{
        position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)',
        width: 800, height: 400,
        background: 'radial-gradient(ellipse at 50% 0%, rgba(45, 212, 191, 0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', maxWidth: 1200, margin: '0 auto', padding: '40px 24px 32px' }}>

        {/* ════════ HEADER ════════ */}
        <header style={{ textAlign: 'center', marginBottom: 48 }}>
          <div className="display" style={{
            fontSize: 11, fontWeight: 600, color: 'var(--teal)',
            letterSpacing: '0.25em', textTransform: 'uppercase', marginBottom: 16,
          }}>
            Vellum Protocol &mdash; Tempo Hackathon 2026
          </div>
          <h1 className="display" style={{
            fontSize: 44, fontWeight: 800, lineHeight: 1.05, letterSpacing: '-0.03em',
            color: 'var(--text)',
          }}>
            Agent&thinsp;&times;&thinsp;Agent<br />
            <span style={{ color: 'var(--teal)' }}>OTC Block Trading</span>
          </h1>
          <p style={{
            fontSize: 13, color: 'var(--text-dim)', maxWidth: 520,
            margin: '16px auto 0', lineHeight: 1.7, letterSpacing: '0.01em',
          }}>
            Two AI agents negotiate a 100,000 TEMPO/USDC block trade across
            12 fields with cross-field concession intelligence.
            Both sides save vs. AMM execution.
          </p>
        </header>

        {/* ════════ CTA ════════ */}
        {phase === 'idle' && (
          <div className="fade-up" style={{ textAlign: 'center', marginBottom: 48 }}>
            <button className="cta-btn" onClick={runDemo}>
              <span>Execute Negotiation</span>
            </button>
            {error && <p style={{ color: 'var(--red)', marginTop: 16, fontSize: 12 }}>{error}</p>}
          </div>
        )}

        {phase !== 'idle' && (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 20, marginBottom: 32 }}>
            {/* Status indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div className={phase === 'done' ? '' : 'pulse'} style={{
                width: 8, height: 8, borderRadius: '50%',
                background: phase === 'done' ? 'var(--lime)' : phase === 'settling' ? 'var(--amber)' : 'var(--teal)',
              }} />
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>
                {phase === 'market' ? 'Reading market' : phase === 'negotiating' ? 'Agents active' : phase === 'settling' ? 'Settling on-chain' : 'Complete'}
              </span>
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
              {(elapsed / 1000).toFixed(1)}s
            </span>
            {phase === 'done' && (
              <button onClick={runDemo} style={{
                background: 'none', border: '1px solid var(--border-bright)',
                color: 'var(--text-dim)', padding: '6px 16px', fontSize: 11,
                fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                letterSpacing: '0.04em',
              }}>
                RE-RUN
              </button>
            )}
          </div>
        )}

        {/* ════════ MARKET RIBBON ════════ */}
        {market && (
          <div className="fade-up" style={{
            display: 'flex', alignItems: 'center', gap: 0,
            border: '1px solid var(--border)', marginBottom: 20,
            background: 'var(--surface)',
          }}>
            <div style={{ padding: '10px 16px', borderRight: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--lime)' }} />
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>TEMPO/USDC</span>
            </div>
            <Ribbon label="MID" value={`$${market.dex_mid_price}`} />
            <Ribbon label="SLIP" value={`${market.dex_slippage_bps}bp`} color="var(--red)" />
            <Ribbon label="DEPTH" value={`$${fmtK(market.liquidity_depth)}`} />
            <Ribbon label="DEX SELL" value={`$${Number(market.seller_effective_dex_price).toFixed(4)}`} color="var(--seller)" />
            <Ribbon label="DEX BUY" value={`$${Number(market.buyer_effective_dex_price).toFixed(4)}`} color="var(--buyer)" />
          </div>
        )}

        {/* ════════ AGENT IDENTITIES ════════ */}
        {phase !== 'idle' && phase !== 'market' && (
          <div className="fade-in" style={{
            display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 40, marginBottom: 20,
          }}>
            <AgentBadge agent="seller" active={phase === 'negotiating'} />
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <span className="display" style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-muted)' }}>VS</span>
              {counterCount > 0 && (
                <span style={{ fontSize: 10, color: 'var(--amber)', fontWeight: 600 }}>
                  {counterCount} contested
                </span>
              )}
            </div>
            <AgentBadge agent="buyer" active={phase === 'negotiating'} />
          </div>
        )}

        {/* ════════ FIELD TILE GRID + DECISION LOG ════════ */}
        {phase !== 'idle' && phase !== 'market' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 16, marginBottom: 20 }}>

            {/* ── Tile Grid (4 cols x 3 rows) ── */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 2, background: 'var(--border)', padding: 1,
            }}>
              {FIELDS.map((f, idx) => {
                const status = fieldStatuses[f.key] || 'PENDING';
                const val = fieldValues[f.key];
                const displayVal = val ? (f.format ? f.format(val) : `${val}${f.unit ? ' ' + f.unit : ''}`) : '—';
                const tileClass = status === 'AGREED' ? 'tile-agreed' : status === 'COUNTER_PROPOSED' ? 'tile-counter' : status === 'PROPOSED' ? 'tile-proposed' : 'tile-pending';

                return (
                  <div key={f.key} className={`tile ${tileClass}`} style={{
                    background: 'var(--surface)',
                    padding: '14px 12px',
                    display: 'flex', flexDirection: 'column', gap: 6,
                    position: 'relative', overflow: 'hidden',
                    animationDelay: `${idx * 40}ms`,
                  }}>
                    {/* Status indicator line at top */}
                    <div style={{
                      position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                      background: status === 'AGREED' ? 'var(--lime)'
                        : status === 'COUNTER_PROPOSED' ? 'var(--amber)'
                        : status === 'PROPOSED' ? 'var(--teal)'
                        : 'transparent',
                      transition: 'background 0.3s ease',
                    }} />

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
                        color: status === 'AGREED' ? 'var(--lime)' : 'var(--text-muted)',
                      }}>
                        {f.label}
                      </span>
                      {status === 'AGREED' && (
                        <span style={{ fontSize: 10, color: 'var(--lime)' }}>&#10003;</span>
                      )}
                      {status === 'COUNTER_PROPOSED' && (
                        <span style={{ fontSize: 8, color: 'var(--amber)', fontWeight: 700, letterSpacing: '0.05em' }}>CONTESTED</span>
                      )}
                    </div>

                    <div style={{
                      fontSize: status === 'PENDING' ? 14 : 16,
                      fontWeight: 600,
                      color: status === 'PENDING' ? 'var(--text-muted)'
                        : status === 'AGREED' ? 'var(--text)'
                        : status === 'COUNTER_PROPOSED' ? 'var(--amber)'
                        : 'var(--teal)',
                      fontVariantNumeric: 'tabular-nums',
                      transition: 'all 0.3s ease',
                    }}>
                      {displayVal}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* ── Decision Feed ── */}
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}>
              <div style={{
                padding: '10px 14px', borderBottom: '1px solid var(--border)',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                flexShrink: 0,
              }}>
                <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-muted)' }}>
                  DECISION FEED
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                  {visibleActions.length}{result ? ` / ${result.total_actions}` : ''}
                </span>
              </div>

              <div ref={logRef} style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
                {visibleActions.map((a, i) => (
                  <div key={i} className="entry-slide" style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '5px 14px',
                    borderLeft: `2px solid ${a.agent === 'seller' ? 'var(--seller)' : 'var(--buyer)'}`,
                    background: a.decision === 'COUNTER' ? 'var(--amber-dim)' : 'transparent',
                    animationDelay: '0ms',
                  }}>
                    <span style={{
                      fontSize: 9, fontWeight: 700, width: 16, textAlign: 'right',
                      color: 'var(--text-muted)', flexShrink: 0,
                    }}>
                      {i + 1}
                    </span>

                    <span style={{
                      fontSize: 9, fontWeight: 700, letterSpacing: '0.04em',
                      padding: '1px 5px',
                      color: a.decision === 'ACCEPT' ? 'var(--lime)' : a.decision === 'COUNTER' ? 'var(--amber)' : 'var(--red)',
                      background: a.decision === 'ACCEPT' ? 'var(--lime-dim)' : a.decision === 'COUNTER' ? 'var(--amber-dim)' : 'var(--red-dim)',
                      flexShrink: 0,
                    }}>
                      {a.decision === 'ACCEPT' ? 'ACC' : a.decision === 'COUNTER' ? 'CTR' : a.decision.slice(0, 3)}
                    </span>

                    <span style={{
                      fontSize: 10, fontWeight: 600, width: 80,
                      color: 'var(--teal)', flexShrink: 0,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {FIELDS.find(f => f.key === a.field_path)?.label || a.field_path}
                    </span>

                    <span style={{
                      fontSize: 10, color: 'var(--text-muted)',
                      flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {a.reasoning.replace('[AUTO-LLM] ', '').replace('Initiated proposal: success', 'proposed')}
                    </span>

                    {a.counter_value && (
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', flexShrink: 0 }}>
                        &rarr;&thinsp;{a.counter_value}
                      </span>
                    )}
                  </div>
                ))}

                {phase === 'negotiating' && visibleActions.length < (result?.total_actions || 999) && (
                  <div className="pulse" style={{
                    padding: '8px 14px', fontSize: 10, color: 'var(--text-muted)',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--teal)' }} />
                    processing...
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ════════ SETTLEMENT + SAVINGS ════════ */}
        {(phase === 'settling' || phase === 'done') && (
          <div className="fade-up" style={{
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            animation: phase === 'settling' ? 'borderPulse 1.5s ease-in-out infinite' : undefined,
            marginBottom: 20,
          }}>
            {/* Settlement header */}
            <div style={{
              padding: '12px 20px', borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <div className={phase === 'settling' ? 'pulse' : ''} style={{
                width: 8, height: 8, borderRadius: '50%',
                background: phase === 'done' ? 'var(--lime)' : 'var(--amber)',
              }} />
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase',
                color: phase === 'done' ? 'var(--lime)' : 'var(--amber)',
              }}>
                {phase === 'settling' ? 'MPP settlement on Tempo chain...' : 'Settled via MPP — atomic swap confirmed'}
              </span>
              {phase === 'done' && result && (
                <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  {result.entity_id}
                </span>
              )}
            </div>

            {/* Savings */}
            {phase === 'done' && result?.savings_vs_dex && (
              <div style={{ padding: '24px 20px' }}>
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 32,
                }}>
                  <SavedMetric
                    label="AGREED PRICE"
                    value={`$${result.savings_vs_dex.otc_price}`}
                    sub="per TEMPO token"
                  />
                  <SavedMetric
                    label="AMM SLIPPAGE"
                    value={`${result.savings_vs_dex.dex_slippage_bps}bp`}
                    sub={`on ${result.savings_vs_dex.quantity.toLocaleString()} tokens`}
                    color="var(--red)"
                  />
                  <SavedMetric
                    label="SELLER SAVES"
                    value={`$${fmtK(result.savings_vs_dex.seller_savings)}`}
                    sub="vs. selling on DEX"
                    color="var(--lime)"
                  />
                  <SavedMetric
                    label="BUYER SAVES"
                    value={`$${fmtK(result.savings_vs_dex.buyer_savings)}`}
                    sub="vs. buying on DEX"
                    color="var(--lime)"
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* ════════ FOOTER ════════ */}
        <footer style={{
          textAlign: 'center', paddingTop: 32, paddingBottom: 24,
          fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em',
        }}>
          BUILT WITH <span style={{ color: 'var(--teal)' }}>VELLUM</span> NEGOTIATION ENGINE
          &ensp;&middot;&ensp;
          SETTLES VIA <span style={{ color: 'var(--lime)' }}>MPP</span> ON <span style={{ color: 'var(--lime)' }}>TEMPO</span> CHAIN
        </footer>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Sub-components
   ═══════════════════════════════════════════════════════════════ */

function Ribbon({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      padding: '10px 16px', borderRight: '1px solid var(--border)',
      display: 'flex', alignItems: 'baseline', gap: 6,
    }}>
      <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: color || 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  );
}

function AgentBadge({ agent, active }: { agent: 'seller' | 'buyer'; active: boolean }) {
  const isSeller = agent === 'seller';
  const color = isSeller ? 'var(--seller)' : 'var(--buyer)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {/* Geometric avatar */}
      <div style={{
        width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `1.5px solid ${color}`,
        borderRadius: isSeller ? 2 : 16,
        background: isSeller ? 'var(--seller-dim)' : 'var(--buyer-dim)',
        transform: isSeller ? 'rotate(45deg)' : 'none',
      }}>
        <span style={{
          fontSize: 12, fontWeight: 700, color,
          transform: isSeller ? 'rotate(-45deg)' : 'none',
        }}>
          {isSeller ? 'S' : 'B'}
        </span>
      </div>
      <div>
        <div className="display" style={{ fontSize: 13, fontWeight: 700, color }}>{isSeller ? 'Seller' : 'Buyer'}</div>
        <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
          {active ? (
            <span className="pulse" style={{ color }}>ACTIVE</span>
          ) : 'AI AGENT'}
        </div>
      </div>
    </div>
  );
}

function SavedMetric({ label, value, sub, color }: { label: string; value: string; sub: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 6 }}>
        {label}
      </div>
      <div className="scale-in" style={{
        fontSize: 28, fontWeight: 700, color: color || 'var(--text)',
        fontVariantNumeric: 'tabular-nums', lineHeight: 1,
      }}>
        {value}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

function fmtK(v: string | number) {
  const n = typeof v === 'string' ? Number(v) : v;
  if (isNaN(n)) return String(v);
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}
