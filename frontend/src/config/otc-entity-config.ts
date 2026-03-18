import type { EntityUIConfig } from '@vellum/ui/schema';

/**
 * OTCBlockTrade — Entity UI Config for Vellum SDK
 *
 * Maps the 12 negotiable fields into form sections and table columns.
 * This is the ONLY place the UI knows about OTC domain specifics.
 */
export const otcBlockTradeConfig: EntityUIConfig = {
  typeName: 'OTCBlockTrade',

  sections: [
    {
      id: 'economics',
      title: 'Economics',
      fields: ['price_per_token', 'quantity', 'min_fill_quantity'],
    },
    {
      id: 'execution',
      title: 'Execution',
      fields: [
        'partial_fill_allowed',
        'settlement_window_secs',
        'execution_tranches',
        'max_slippage_bps',
      ],
    },
    {
      id: 'trust',
      title: 'Trust & Risk',
      fields: ['escrow_pct', 'penalty_bps', 'expire_after_secs'],
    },
    {
      id: 'market_reference',
      title: 'Market Reference',
      fields: ['price_oracle_source', 'twap_window_mins'],
    },
  ],

  fields: {
    price_per_token: { type: 'number', label: 'Price per Token', required: true },
    quantity: { type: 'number', label: 'Block Size (tokens)', required: true },
    min_fill_quantity: { type: 'number', label: 'Min Fill Quantity' },
    partial_fill_allowed: { type: 'boolean', label: 'Partial Fill Allowed' },
    settlement_window_secs: { type: 'number', label: 'Settlement Window (s)' },
    execution_tranches: { type: 'number', label: 'Execution Tranches' },
    max_slippage_bps: { type: 'number', label: 'Max Slippage (bps)' },
    escrow_pct: { type: 'number', label: 'Escrow (%)' },
    penalty_bps: { type: 'number', label: 'Penalty (bps)' },
    expire_after_secs: { type: 'number', label: 'Expiry (s)' },
    price_oracle_source: { type: 'string', label: 'Oracle Source' },
    twap_window_mins: { type: 'number', label: 'TWAP Window (min)' },
  },

  columns: [
    { fieldPath: 'id', header: 'Trade ID', sortable: true },
    { fieldPath: 'status', header: 'Status', sortable: true },
    { fieldPath: 'price_per_token', header: 'Price', sortable: true },
    { fieldPath: 'quantity', header: 'Qty', sortable: true },
    { fieldPath: 'seller_id', header: 'Seller' },
    { fieldPath: 'buyer_id', header: 'Buyer' },
    { fieldPath: 'created_at', header: 'Created', sortable: true },
  ],

  negotiableFields: [
    'price_per_token',
    'quantity',
    'min_fill_quantity',
    'partial_fill_allowed',
    'settlement_window_secs',
    'execution_tranches',
    'max_slippage_bps',
    'escrow_pct',
    'penalty_bps',
    'expire_after_secs',
    'price_oracle_source',
    'twap_window_mins',
  ],
};
