'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import * as adminService from '@/services/admin.service';
import type { ProviderConfig } from '@/types/api';

type Draft = Pick<ProviderConfig, 'display_name' | 'model' | 'credit_cost'>;

export default function AdminModelsPage() {
  const [configs, setConfigs] = useState<ProviderConfig[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void adminService
      .listProviderConfigs()
      .then((items) => {
        setConfigs(items);
        setDrafts(
          Object.fromEntries(
            items.map((c) => [
              c.id,
              { display_name: c.display_name, model: c.model, credit_cost: c.credit_cost },
            ]),
          ),
        );
      })
      .catch(() => setConfigs([]));
  }, []);

  const isDirty = (config: ProviderConfig) => {
    const draft = drafts[config.id];
    return (
      !!draft &&
      (draft.display_name !== config.display_name ||
        draft.model !== config.model ||
        draft.credit_cost !== config.credit_cost)
    );
  };

  const patch = async (id: string, changes: Partial<Draft> & { is_enabled?: boolean }) => {
    setBusyId(id);
    setError(null);
    try {
      const updated = await adminService.updateProviderConfig(id, changes);
      setConfigs((prev) => prev?.map((c) => (c.id === id ? updated : c)) ?? null);
      setDrafts((d) => ({
        ...d,
        [id]: {
          display_name: updated.display_name,
          model: updated.model,
          credit_cost: updated.credit_cost,
        },
      }));
    } catch {
      setError('Could not save. Please try again.');
    } finally {
      setBusyId(null);
    }
  };

  const edit = (id: string, changes: Partial<Draft>) =>
    setDrafts((d) => {
      const current = d[id];
      return current ? { ...d, [id]: { ...current, ...changes } } : d;
    });

  if (configs === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        The real provider and model behind each slot. Disabling one stops it being offered to
        customers. Credit costs apply per operation. The names customers actually see are on the{' '}
        <span className="font-medium text-foreground">Branding</span> tab.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {configs.map((config) => {
        const draft = drafts[config.id] ?? {
          display_name: '',
          model: '',
          credit_cost: 0,
        };
        return (
          <div key={config.id} className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2">
              <Badge variant="outline" className="capitalize">
                {config.capability}
              </Badge>
              <span className="text-xs text-muted-foreground">{config.provider}</span>
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {config.is_enabled ? 'Enabled' : 'Disabled'}
                </span>
                <Switch
                  checked={config.is_enabled}
                  disabled={busyId === config.id}
                  onCheckedChange={(checked) => void patch(config.id, { is_enabled: checked })}
                />
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor={`name-${config.id}`} className="text-xs">
                  Admin label
                </Label>
                <Input
                  id={`name-${config.id}`}
                  className="h-8"
                  value={draft.display_name}
                  maxLength={100}
                  onChange={(e) => edit(config.id, { display_name: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`model-${config.id}`} className="text-xs">
                  Model ID
                </Label>
                <Input
                  id={`model-${config.id}`}
                  className="h-8 font-mono text-xs"
                  value={draft.model}
                  onChange={(e) => edit(config.id, { model: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`cost-${config.id}`} className="text-xs">
                  Credits per use
                </Label>
                <Input
                  id={`cost-${config.id}`}
                  type="number"
                  min={0}
                  className="h-8"
                  value={draft.credit_cost}
                  onChange={(e) => edit(config.id, { credit_cost: Number(e.target.value) })}
                />
              </div>
            </div>

            {isDirty(config) && (
              <Button
                size="sm"
                className="mt-3"
                disabled={busyId === config.id}
                onClick={() => {
                  const draftToSave = drafts[config.id];
                  if (draftToSave) void patch(config.id, draftToSave);
                }}
              >
                {busyId === config.id && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                Save
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
