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

/** One wallet, in credits. One credit is one rupee. */
export interface Credits {
  balance: number;
}

export interface UsageRecord {
  id: string;
  /** Opaque slot key — render via lib/model-labels, never show the raw value to users. */
  provider: string;
  operation: string;
  credits_consumed: number;
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
  /** What the vendor bills us per operation, in rupees. Decimal string from the API. */
  provider_cost_inr: string;
  /** Charged to the customer before margin, in credits. */
  credit_cost: number;
  /** Profit added per operation, in credits. Charged per generated image. */
  margin_credits: number;
  /** credit_cost + margin_credits — what the wallet is actually debited by. */
  charge_credits: number;
  /** charge_credits − provider_cost_inr, in rupees. Decimal string from the API. */
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
  base_credits: number;
  margin_credits: number;
  charge_credits: number;
  profit_per_op_inr: string;
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
