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
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

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
  created_at: string;
  results: GenerationResult[];
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  description: string | null;
  price: string;
  currency: string;
  billing_interval: string;
  monthly_chat_credits: number;
  monthly_image_credits: number;
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

export interface Credits {
  chat_balance: number;
  image_balance: number;
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
  credit_cost: number;
  display_name: string;
}
