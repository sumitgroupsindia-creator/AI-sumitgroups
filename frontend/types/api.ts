export type ProviderName = 'openai' | 'gemini';

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_admin: boolean;
  is_verified: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Conversation {
  id: string;
  title: string;
  /** Opaque slot key — render via lib/model-labels, never show the raw value to users. */
  provider: ProviderName;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  provider: string | null;
  error: string | null;
  /** An image the user attached to this turn. */
  upload_file_id: string | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
  /** Images generated from inside this thread; interleaved with `messages` by created_at. */
  generations: GenerationRequest[];
}

/** Which model slots a turn should run through. 'both' asks every enabled slot. */
export type ModelSelection = ProviderName | 'both';

/** Whether the composer is asking for words or for pictures. */
export type ComposerMode = 'chat' | 'image';

export type GenerationStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface GenerationResult {
  id: string;
  /** Opaque slot key — render via lib/model-labels, never show the raw value to users. */
  provider: ProviderName;
  status: GenerationStatus;
  error: string | null;
  image_url: string | null;
  thumbnail_url: string | null;
  created_at: string;
}

export interface GenerationRequest {
  id: string;
  prompt: string;
  status: 'pending' | 'processing' | 'completed' | 'partial' | 'failed';
  conversation_id: string | null;
  upload_file_id: string | null;
  created_at: string;
  results: GenerationResult[];
}

export interface UploadedFile {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  created_at: string;
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  description: string | null;
  price: string;
  currency: string;
  billing_interval: string;
  /** One wallet, one credit = ₹1. Granted afresh each billing period. */
  monthly_credits: number;
  max_upload_mb: number;
  priority_queue: boolean;
}

export interface Subscription {
  id: string;
  status: string;
  provider: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  plan: Plan;
}

/**
 * One wallet, in credits. One credit is one rupee.
 *
 * Fractional: a chat turn is metered on real token counts and costs a fraction of a rupee. Render
 * it with `formatCredits`, never raw — the API sends four decimal places and almost none of them
 * are worth showing.
 */
export interface Credits {
  balance: number;
}

export interface UsageRecord {
  id: string;
  /** Opaque slot key — render via lib/model-labels, never show the raw value to users. */
  provider: string;
  operation: string;
  /** Fractional on metered operations — a chat turn costs a fraction of a credit. */
  credits_consumed: number;
  /** What the vendor reported processing. Null on flat-priced operations and on older records. */
  input_tokens: number | null;
  output_tokens: number | null;
  status: string;
  created_at: string;
}

export interface CheckoutResponse {
  provider: string;
  order_id: string;
  amount: number;
  currency: string;
  key_id: string;
  subscription_id: string;
}

export interface AdminStats {
  total_users: number;
  active_subscriptions: number;
  total_conversations: number;
  total_generation_requests: number;
  failed_generations_last_24h: number;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

/** One customer's spend on one slot, for one kind of operation. Admin-only. */
export interface AdminUsageBreakdownRow {
  provider: string;
  operation: string;
  operations: number;
  credits_charged: number;
  /** What the vendor actually billed us. Never exposed on customer-facing endpoints. */
  vendor_cost_inr: string;
  profit_inr: string;
  input_tokens: number;
  output_tokens: number;
}

/** One ledger line as an administrator sees it — vendor cost included. */
export interface AdminUserUsageRecord {
  id: string;
  provider: string;
  model: string;
  operation: string;
  credits_consumed: number;
  cost_inr: string;
  input_tokens: number | null;
  output_tokens: number | null;
  status: string;
  error: string | null;
  created_at: string;
}

/** Everything about one customer: who, which plan, what is left, and what they cost us. */
export interface AdminUserDetail {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;

  plan_code: string | null;
  plan_name: string | null;
  plan_price: string | null;
  plan_monthly_credits: number | null;
  subscription_status: string | null;
  current_period_end: string | null;

  credits_balance: number;

  total_operations: number;
  total_credits_charged: number;
  total_vendor_cost_inr: string;
  total_profit_inr: string;
  total_input_tokens: number;
  total_output_tokens: number;

  breakdown: AdminUsageBreakdownRow[];
  recent: AdminUserUsageRecord[];
}

/** Admin-only: administrators configure providers, so they do see real vendor names and model ids. */
export interface AdminGenerationResult extends GenerationResult {
  model: string;
}

export interface ProviderConfig {
  id: string;
  provider: string;
  capability: 'chat' | 'image';
  model: string;
  is_enabled: boolean;
  /** What the vendor bills us per flat-priced operation, in rupees. Decimal string from the API. */
  provider_cost_inr: string;
  /** Flat credits added on top of the vendor's bill. This is the profit. Decimal string. */
  margin_credits: string;
  /** Rupees per million input tokens. Non-zero switches this slot to metered billing. */
  input_cost_per_mtok_inr: string;
  /** Rupees per million output tokens. */
  output_cost_per_mtok_inr: string;
  /** What the customer pays per rupee of vendor cost. 1.0 sells at cost. Decimal string. */
  markup_multiplier: string;
  /** True when this slot is billed on real token counts rather than per operation. */
  is_metered: boolean;
  /** What one operation charges. Exact when flat; a representative turn when metered. */
  charge_credits: number;
  /** The margin, in rupees — the charge is the vendor's bill plus it. Decimal string. */
  profit_inr: string;
  display_name: string;
}

/** One slot's current price beside what it earned over the reporting window. Admin-only. */
export interface AdminPricingRow {
  provider: string;
  capability: 'chat' | 'image';
  model: string;
  display_name: string;
  is_enabled: boolean;
  cost_inr: string;
  margin_credits: string;
  charge_credits: number;
  profit_per_op_inr: string;
  is_metered: boolean;
  operations: number;
  revenue_inr: string;
  spend_inr: string;
  profit_inr: string;
}

export interface AdminPricing {
  days: number;
  rows: AdminPricingRow[];
  total_operations: number;
  total_revenue_inr: string;
  total_spend_inr: string;
  total_profit_inr: string;
}

/**
 * One master prompt the product adds to every request. Editable at /admin/prompts.
 *
 * `kind` decides when it applies: `base` always, `task` when the router picks it for a request,
 * `tool` for the machinery itself (the router, and reading an attached photo) — switching a tool
 * off turns that step and its API cost off.
 */
export interface PromptTemplate {
  id: string;
  key: string;
  scope: 'chat' | 'image';
  kind: 'base' | 'task' | 'tool';
  name: string;
  /** Read by the router when deciding whether a task fits, so this changes behaviour. */
  description: string;
  content: string;
  is_enabled: boolean;
  sort_order: number;
}

/** How a provider slot is named for customers. Editable at /admin/branding. */
export interface ProviderBrand {
  id: string;
  provider: string;
  slot: string;
  tier: string;
  description: string;
  sort_order: number;
}

/** The public, unauthenticated view of a slot — branding and prices, never model identifiers. */
export interface PublicModelSlot {
  provider: string;
  slot: string;
  tier: string;
  description: string;
  chat_enabled: boolean;
  image_enabled: boolean;
  /** Free accounts cannot select this slot; the composer shows it locked. */
  requires_paid_plan: boolean;
  chat_credit_cost: number;
  image_credit_cost: number;
}

export type SettingKind = 'string' | 'int' | 'bool' | 'secret' | 'select';

export interface AdminSetting {
  key: string;
  label: string;
  group: string;
  kind: SettingKind;
  help: string;
  options: string[];
  /** Always empty for secrets — the API never returns them in readable form. */
  value: string;
  masked: string;
  is_secret: boolean;
  is_set: boolean;
  source: 'database' | 'environment';
  /** Sealed with an encryption key this deployment no longer holds; must be re-entered. */
  unreadable: boolean;
}

export interface AdminSettingAudit {
  id: string;
  key: string;
  actor_email: string;
  old_preview: string;
  new_preview: string;
  created_at: string;
}
