'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import * as adminService from '@/services/admin.service';
import type { AdminStats } from '@/types/api';

const CARDS: { key: keyof AdminStats; label: string }[] = [
  { key: 'total_users', label: 'Total users' },
  { key: 'active_subscriptions', label: 'Active subscriptions' },
  { key: 'total_conversations', label: 'Conversations' },
  { key: 'total_generation_requests', label: 'Image generations' },
  { key: 'failed_generations_last_24h', label: 'Failures (24h)' },
];

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);

  useEffect(() => {
    void adminService.getStats().then(setStats).catch(() => setStats(null));
  }, []);

  if (!stats) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {CARDS.map((card) => (
        <Card key={card.key}>
          <CardHeader className="pb-2">
            <CardDescription>{card.label}</CardDescription>
            <CardTitle className="text-3xl tabular-nums">{stats[card.key]}</CardTitle>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}
