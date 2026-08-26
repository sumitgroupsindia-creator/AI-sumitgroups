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

type Draft = {
  display_name: string;
  model: string;
  provider_cost_inr: number;
  credit_cost: number;
  margin_credits: number;
};

const rupees = (value: number) =>
  `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function draftOf(config: ProviderConfig): Draft {
  return {
    display_name: config.display_name,
    model: config.model,
    provider_cost_inr: Number.parseFloat(config.provider_cost_inr),
    credit_cost: config.credit_cost,
    margin_credits: config.margin_credits,
  };
}

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
        setDrafts(Object.fromEntries(items.map((c) => [c.id, draftOf(c)])));
      })
      .catch(() => setConfigs([]));
  }, []);

  const isDirty = (config: ProviderConfig) => {
    const draft = drafts[config.id];
    if (!draft) return false;
    const saved = draftOf(config);
    return (Object.keys(saved) as (keyof Draft)[]).some((key) => draft[key] !== saved[key]);
  };

  const patch = async (id: string, changes: Partial<Draft> & { is_enabled?: boolean }) => {
    setBusyId(id);
    setError(null);
    try {
      const updated = await adminService.updateProviderConfig(id, changes);
      setConfigs((prev) => prev?.map((c) => (c.id === id ? updated : c)) ?? null);
      setDrafts((d) => ({ ...d, [id]: draftOf(updated) }));
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
        The real provider and model behind each slot, and what using it earns. One credit is one
        rupee: the customer pays <span className="font-medium text-foreground">base + margin</span>,
        we pay the vendor, and the difference is the profit. Margin is charged per operation — asking
        both slots for an image bills it twice, because it costs us twice. The names customers see
        are on the <span className="font-medium text-foreground">Branding</span> tab.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {configs.map((config) => {
        const draft = drafts[config.id];
        if (!draft) return null;
        // Previewed from the draft, not from the saved row, so the effect of a change is visible
        // before it is committed.
        const charge = draft.credit_cost + draft.margin_credits;
        const profit = charge - draft.provider_cost_inr;

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

            <div className="grid gap-3 sm:grid-cols-2">
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
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor={`cost-${config.id}`} className="text-xs">
                  Our cost (₹ per use)
                </Label>
                <Input
                  id={`cost-${config.id}`}
                  type="number"
                  min={0}
                  step="0.0001"
                  className="h-8"
                  value={draft.provider_cost_inr}
                  onChange={(e) => edit(config.id, { provider_cost_inr: Number(e.target.value) })}
                />
                <p className="text-[11px] text-muted-foreground">What the vendor bills us.</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`base-${config.id}`} className="text-xs">
                  Base credits
                </Label>
                <Input
                  id={`base-${config.id}`}
                  type="number"
                  min={0}
                  className="h-8"
                  value={draft.credit_cost}
                  onChange={(e) => edit(config.id, { credit_cost: Number(e.target.value) })}
                />
                <p className="text-[11px] text-muted-foreground">
                  Cover cost: at least {Math.ceil(draft.provider_cost_inr)}.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`margin-${config.id}`} className="text-xs">
                  Margin credits
                </Label>
                <Input
                  id={`margin-${config.id}`}
                  type="number"
                  min={0}
                  className="h-8"
                  value={draft.margin_credits}
                  onChange={(e) => edit(config.id, { margin_credits: Number(e.target.value) })}
                />
                <p className="text-[11px] text-muted-foreground">Profit added on top.</p>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-muted/60 px-3 py-2 text-xs">
              <span>
                Customer pays{' '}
                <span className="font-medium tabular-nums">
                  {charge} credit{charge === 1 ? '' : 's'}
                </span>{' '}
                ({rupees(charge)})
              </span>
              <span className="text-muted-foreground">
                cost {rupees(draft.provider_cost_inr)}
              </span>
              <span
                className={
                  profit > 0 ? 'font-medium text-emerald-600' : 'font-medium text-destructive'
                }
              >
                profit {rupees(profit)}
              </span>
              {profit <= 0 && (
                <span className="text-destructive">
                  — every use loses money at this price.
                </span>
              )}
            </div>

            {isDirty(config) && (
              <Button
                size="sm"
                className="mt-3"
                disabled={busyId === config.id}
                onClick={() => void patch(config.id, draft)}
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
