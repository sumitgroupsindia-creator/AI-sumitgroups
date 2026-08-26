'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import * as adminService from '@/services/admin.service';
import type { AdminPricing } from '@/types/api';

const WINDOWS = [7, 30, 90] as const;

const rupees = (value: string | number) =>
  `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function AdminPricingPage() {
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<AdminPricing | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void adminService
      .getPricing(days)
      .then((result) => !cancelled && setData(result))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [days]);

  if (loading && !data) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;
  if (!data) return <p className="text-sm text-destructive">Could not load pricing.</p>;

  const profit = Number(data.total_profit_inr);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <p className="flex-1 text-sm text-muted-foreground">
          What each slot charges now, and what it actually earned. Revenue and cost come from the
          usage ledger as it was recorded, so changing a price today never rewrites what last month
          made. Refunded failures are excluded — they earned nothing.
        </p>
        <div className="inline-flex rounded-md border p-0.5">
          {WINDOWS.map((window) => (
            <button
              key={window}
              type="button"
              onClick={() => setDays(window)}
              className={cn(
                'rounded px-3 py-1 text-xs font-medium transition-colors',
                days === window
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {window}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Operations</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {data.total_operations.toLocaleString('en-IN')}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Revenue</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{rupees(data.total_revenue_inr)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Provider cost</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{rupees(data.total_spend_inr)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Profit</CardDescription>
            <CardTitle
              className={cn(
                'text-2xl tabular-nums',
                profit > 0 ? 'text-emerald-600' : profit < 0 ? 'text-destructive' : undefined,
              )}
            >
              {rupees(data.total_profit_inr)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-3 font-medium">Slot</th>
              <th className="px-4 py-3 font-medium">Our cost</th>
              <th className="px-4 py-3 font-medium">Base</th>
              <th className="px-4 py-3 font-medium">Margin</th>
              <th className="px-4 py-3 font-medium">Customer pays</th>
              <th className="px-4 py-3 font-medium">Profit / use</th>
              <th className="px-4 py-3 font-medium">Uses</th>
              <th className="px-4 py-3 font-medium">Revenue</th>
              <th className="px-4 py-3 font-medium">Cost</th>
              <th className="px-4 py-3 font-medium">Profit</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => {
              const perUse = Number(row.profit_per_op_inr);
              const total = Number(row.profit_inr);
              return (
                <tr key={`${row.provider}-${row.capability}`} className="border-t">
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="capitalize">
                        {row.capability}
                      </Badge>
                      <span className="text-muted-foreground">{row.provider}</span>
                      {!row.is_enabled && (
                        <Badge variant="secondary" className="text-[10px]">
                          off
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 tabular-nums text-muted-foreground">
                    {rupees(row.cost_inr)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.base_credits}</td>
                  <td className="px-4 py-3 tabular-nums">+{row.margin_credits}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-medium tabular-nums">
                    {row.charge_credits} cr
                  </td>
                  <td
                    className={cn(
                      'whitespace-nowrap px-4 py-3 tabular-nums',
                      perUse > 0 ? 'text-emerald-600' : perUse < 0 ? 'text-destructive' : undefined,
                    )}
                  >
                    {rupees(perUse)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.operations.toLocaleString('en-IN')}</td>
                  <td className="whitespace-nowrap px-4 py-3 tabular-nums">{rupees(row.revenue_inr)}</td>
                  <td className="whitespace-nowrap px-4 py-3 tabular-nums text-muted-foreground">
                    {rupees(row.spend_inr)}
                  </td>
                  <td
                    className={cn(
                      'whitespace-nowrap px-4 py-3 font-medium tabular-nums',
                      total > 0 ? 'text-emerald-600' : total < 0 ? 'text-destructive' : undefined,
                    )}
                  >
                    {rupees(row.profit_inr)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
