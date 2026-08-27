'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import * as adminService from '@/services/admin.service';
import { formatCredits, formatDate, formatDateTime } from '@/lib/utils';
import type { AdminUserDetail } from '@/types/api';

const OPERATION_LABEL: Record<string, string> = {
  chat: 'Chat',
  image_generate: 'Image',
  image_edit: 'Image edit',
  assist_route: 'Style routing',
  assist_vision: 'Photo reading',
};

const rupees = (value: string | number) =>
  `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * One customer's account, end to end.
 *
 * The two numbers that matter sit side by side deliberately: what we charged them, and what OpenAI
 * or Google charged us for the same work. Everywhere else in the product the second number is
 * hidden — it is our supplier price — so this is the only screen where the margin on a single
 * customer can actually be read.
 */
export default function AdminUserDetailPage() {
  const params = useParams<{ userId: string }>();
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.userId) return;
    void adminService
      .getUserDetail(params.userId)
      .then(setDetail)
      .catch(() => setError('यह user नहीं मिला।'));
  }, [params?.userId]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!detail) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  const profit = Number(detail.total_profit_inr);

  return (
    <div className="space-y-6">
      <Link
        href="/admin/users"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        सारे users
      </Link>

      {/* ------------------------------------------------------------- who */}
      <div className="rounded-xl border p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{detail.full_name || detail.email}</h2>
            <p className="text-sm text-muted-foreground">{detail.email}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Joined {formatDate(detail.created_at)}
            </p>
          </div>
          <div className="flex gap-2">
            {detail.is_admin && <Badge variant="outline">Admin</Badge>}
            <Badge variant={detail.is_active ? 'success' : 'destructive'}>
              {detail.is_active ? 'Active' : 'Disabled'}
            </Badge>
          </div>
        </div>
      </div>

      {/* --------------------------------------------------- plan & wallet */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border p-5">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Plan</p>
          {detail.plan_name ? (
            <>
              <p className="mt-1.5 text-xl font-semibold">{detail.plan_name}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {detail.plan_price !== null && rupees(detail.plan_price)}
                {detail.plan_monthly_credits !== null &&
                  ` · ${detail.plan_monthly_credits} credits/month`}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {detail.subscription_status && (
                  <Badge variant="outline" className="text-[10px] capitalize">
                    {detail.subscription_status}
                  </Badge>
                )}
                {detail.current_period_end && (
                  <span>renews {formatDate(detail.current_period_end)}</span>
                )}
              </div>
            </>
          ) : (
            // Never subscribed is not the same as being on the free plan, and saying "Free" here
            // would make an account that has never paid look like a deliberate choice.
            <p className="mt-1.5 text-sm text-muted-foreground">कोई subscription नहीं</p>
          )}
        </div>

        <div className="rounded-xl border p-5">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Credits left</p>
          <p className="mt-1.5 text-3xl font-semibold tabular-nums">
            {formatCredits(detail.credits_balance)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">1 credit = ₹1</p>
        </div>
      </div>

      {/* ------------------------------------------------------- the money */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Operations" value={String(detail.total_operations)} />
        <Stat
          label="Charged (revenue)"
          value={rupees(detail.total_credits_charged)}
          hint={`${formatCredits(detail.total_credits_charged)} credits`}
        />
        <Stat
          label="Vendor cost"
          value={rupees(detail.total_vendor_cost_inr)}
          hint="what OpenAI / Gemini billed us"
        />
        <Stat
          label="Profit"
          value={rupees(profit)}
          tone={profit >= 0 ? 'good' : 'bad'}
          hint={`${detail.total_input_tokens.toLocaleString('en-IN')} in / ${detail.total_output_tokens.toLocaleString('en-IN')} out tokens`}
        />
      </div>

      {/* --------------------------------------------------- per-slot rows */}
      <Section title="Breakdown" subtitle="हर slot और operation पर कितना कमाया, कितना खर्च हुआ।">
        {detail.breakdown.length === 0 ? (
          <Empty />
        ) : (
          <Table
            head={['Slot', 'Operation', 'Uses', 'Tokens', 'Charged', 'Vendor cost', 'Profit']}
            rows={detail.breakdown.map((row) => [
              row.provider,
              OPERATION_LABEL[row.operation] ?? row.operation,
              String(row.operations),
              row.input_tokens || row.output_tokens
                ? `${row.input_tokens.toLocaleString('en-IN')} / ${row.output_tokens.toLocaleString('en-IN')}`
                : '—',
              rupees(row.credits_charged),
              rupees(row.vendor_cost_inr),
              rupees(row.profit_inr),
            ])}
          />
        )}
      </Section>

      {/* ------------------------------------------------------- the ledger */}
      <Section title="Recent activity" subtitle="हर call, असली token और असली खर्च के साथ।">
        {detail.recent.length === 0 ? (
          <Empty />
        ) : (
          <Table
            head={['When', 'Slot', 'Model', 'Operation', 'Tokens', 'Charged', 'Cost', 'Status']}
            rows={detail.recent.map((row) => [
              formatDateTime(row.created_at),
              row.provider,
              row.model,
              OPERATION_LABEL[row.operation] ?? row.operation,
              row.input_tokens === null && row.output_tokens === null
                ? '—'
                : `${(row.input_tokens ?? 0).toLocaleString('en-IN')} / ${(row.output_tokens ?? 0).toLocaleString('en-IN')}`,
              formatCredits(row.credits_consumed),
              rupees(row.cost_inr),
              row.status,
            ])}
          />
        )}
      </Section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'good' | 'bad';
}) {
  return (
    <div className="rounded-xl border p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p
        className={
          tone === 'bad'
            ? 'mt-1 text-xl font-semibold tabular-nums text-destructive'
            : tone === 'good'
              ? 'mt-1 text-xl font-semibold tabular-nums text-emerald-500'
              : 'mt-1 text-xl font-semibold tabular-nums'
        }
      >
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mb-2.5 mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
      {children}
    </div>
  );
}

function Empty() {
  return <p className="rounded-xl border p-5 text-sm text-muted-foreground">अभी कुछ नहीं।</p>;
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    // Wide tables scroll inside their own box; the page itself must never scroll sideways.
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            {head.map((cell) => (
              <th key={cell} className="whitespace-nowrap px-4 py-3 font-medium">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={
                    j === 0
                      ? 'whitespace-nowrap px-4 py-3 text-muted-foreground'
                      : 'whitespace-nowrap px-4 py-3 tabular-nums'
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
