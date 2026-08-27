'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useCredits } from '@/hooks/use-credits';
import { useModelLabel } from '@/features/branding/model-branding';
import { modelName } from '@/lib/model-labels';
import { formatCredits, formatDateTime } from '@/lib/utils';
import * as billingService from '@/services/billing.service';
import type { UsageRecord } from '@/types/api';

const OPERATION_LABEL: Record<string, string> = {
  chat: 'Chat message',
  image_generate: 'Image generation',
  image_edit: 'Image edit',
  // The product's own helper calls, made on the way to answering. They are billed to us and never
  // to the customer, which is why they show zero credits — but they burn tokens, so leaving them
  // out would make the token counts on this page fail to add up against the vendor's own figures.
  assist_route: 'Style routing (free)',
  assist_vision: 'Reading your photo (free)',
};

export default function UsageSettingsPage() {
  const labelFor = useModelLabel();
  const { credits, loading: creditsLoading } = useCredits();
  const [records, setRecords] = useState<UsageRecord[] | null>(null);

  useEffect(() => {
    void billingService
      .getUsage()
      .then(setRecords)
      .catch(() => setRecords([]));
  }, []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Credits left</CardDescription>
          <CardTitle className="text-3xl tabular-nums">
            {creditsLoading ? '—' : formatCredits(credits?.balance ?? 0)}
          </CardTitle>
          <CardDescription className="pt-1">
            1 credit = ₹1. Chat and images both draw on this one balance. Chat is metered on
            actual usage, so a short message costs a fraction of a credit.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Every AI operation and what it cost.</CardDescription>
        </CardHeader>
        <CardContent>
          {records === null ? (
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          ) : records.length === 0 ? (
            <p className="text-sm text-muted-foreground">No usage yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Operation</th>
                    <th className="pb-2 pr-4 font-medium">Model</th>
                    <th className="pb-2 pr-4 font-medium">Tokens</th>
                    <th className="pb-2 pr-4 font-medium">Credits</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id} className="border-b last:border-0">
                      <td className="py-2.5 pr-4">{OPERATION_LABEL[record.operation] ?? record.operation}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{modelName(labelFor(record.provider))}</td>
                      <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">
                        {record.input_tokens === null && record.output_tokens === null ? (
                          // Flat-priced work, or a record written before metering existed. A dash
                          // is honest; a zero would claim the vendor processed nothing.
                          <span aria-label="not metered">—</span>
                        ) : (
                          <span title="भेजे गए / मिले टोकन">
                            {(record.input_tokens ?? 0).toLocaleString('en-IN')}
                            {' / '}
                            {(record.output_tokens ?? 0).toLocaleString('en-IN')}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 tabular-nums">
                        {formatCredits(record.credits_consumed)}
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge variant={record.status === 'success' ? 'success' : 'destructive'} className="text-[10px]">
                          {record.status}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap py-2.5 text-muted-foreground">
                        {formatDateTime(record.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
