'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { formatDateTime } from '@/lib/utils';
import * as adminService from '@/services/admin.service';
import type { GenerationResult } from '@/types/api';

export default function AdminFailuresPage() {
  const [failures, setFailures] = useState<GenerationResult[] | null>(null);

  useEffect(() => {
    void adminService.listFailedGenerations().then(setFailures).catch(() => setFailures([]));
  }, []);

  if (failures === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  if (failures.length === 0) {
    return <p className="text-sm text-muted-foreground">No failed generations. </p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-3 font-medium">Provider</th>
            <th className="px-4 py-3 font-medium">Model</th>
            <th className="px-4 py-3 font-medium">Error</th>
            <th className="px-4 py-3 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {failures.map((failure) => (
            <tr key={failure.id} className="border-t">
              <td className="px-4 py-3">
                <Badge variant="secondary" className="capitalize">
                  {failure.provider}
                </Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{failure.model}</td>
              <td className="px-4 py-3">{failure.error ?? '—'}</td>
              <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                {formatDateTime(failure.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
