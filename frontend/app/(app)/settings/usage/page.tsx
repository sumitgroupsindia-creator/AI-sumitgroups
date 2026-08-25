'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useCredits } from '@/hooks/use-credits';
import { useModelLabel } from '@/features/branding/model-branding';
import { formatDateTime } from '@/lib/utils';
import * as billingService from '@/services/billing.service';
import type { UsageRecord } from '@/types/api';

const OPERATION_LABEL: Record<string, string> = {
  chat: 'Chat message',
  image_generate: 'Image generation',
  image_edit: 'Image edit',
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
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Chat credits</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {creditsLoading ? '—' : (credits?.chat_balance ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Image credits</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {creditsLoading ? '—' : (credits?.image_balance ?? 0)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

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
                    <th className="pb-2 pr-4 font-medium">Credits</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id} className="border-b last:border-0">
                      <td className="py-2.5 pr-4">{OPERATION_LABEL[record.operation] ?? record.operation}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{labelFor(record.provider).slot}</td>
                      <td className="py-2.5 pr-4 tabular-nums">{record.credits_consumed}</td>
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
