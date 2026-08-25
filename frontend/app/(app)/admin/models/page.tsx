'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import * as adminService from '@/services/admin.service';
import type { ProviderConfig } from '@/types/api';

export default function AdminModelsPage() {
  const [configs, setConfigs] = useState<ProviderConfig[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, number>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    void adminService.listProviderConfigs().then(setConfigs).catch(() => setConfigs([]));
  }, []);

  const patch = async (id: string, changes: { is_enabled?: boolean; credit_cost?: number }) => {
    setBusyId(id);
    try {
      const updated = await adminService.updateProviderConfig(id, changes);
      setConfigs((prev) => prev?.map((c) => (c.id === id ? updated : c)) ?? null);
    } finally {
      setBusyId(null);
    }
  };

  if (configs === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Disabling a model stops it being offered to users. Credit costs apply per operation, per provider.
      </p>
      {configs.map((config) => (
        <div key={config.id} className="flex flex-wrap items-center gap-4 rounded-lg border p-4">
          <div className="min-w-[10rem] flex-1">
            <p className="font-medium">{config.display_name}</p>
            <p className="text-xs text-muted-foreground">{config.model}</p>
          </div>
          <Badge variant="outline" className="capitalize">
            {config.capability}
          </Badge>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground" htmlFor={`cost-${config.id}`}>
              Credits
            </label>
            <Input
              id={`cost-${config.id}`}
              type="number"
              min={0}
              className="h-8 w-20"
              value={drafts[config.id] ?? config.credit_cost}
              onChange={(e) => setDrafts((d) => ({ ...d, [config.id]: Number(e.target.value) }))}
            />
            {drafts[config.id] !== undefined && drafts[config.id] !== config.credit_cost && (
              <Button
                size="sm"
                disabled={busyId === config.id}
                onClick={() => void patch(config.id, { credit_cost: drafts[config.id] })}
              >
                Save
              </Button>
            )}
          </div>
          <Switch
            checked={config.is_enabled}
            disabled={busyId === config.id}
            onCheckedChange={(checked) => void patch(config.id, { is_enabled: checked })}
          />
        </div>
      ))}
    </div>
  );
}
