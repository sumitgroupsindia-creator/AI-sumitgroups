'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import * as adminService from '@/services/admin.service';
import type { ProviderBrand } from '@/types/api';

type Draft = Pick<ProviderBrand, 'slot' | 'tier' | 'description'>;

/**
 * Renames the slots customers see. Which vendor actually serves a slot is set on the Models tab —
 * the two are deliberately separate so a provider can be swapped without the naming moving with it.
 */
export default function AdminBrandingPage() {
  const [brands, setBrands] = useState<ProviderBrand[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void adminService
      .listProviderBrands()
      .then((items) => {
        setBrands(items);
        setDrafts(
          Object.fromEntries(
            items.map((b) => [b.id, { slot: b.slot, tier: b.tier, description: b.description }]),
          ),
        );
      })
      .catch(() => setBrands([]));
  }, []);

  const isDirty = (brand: ProviderBrand) => {
    const draft = drafts[brand.id];
    return (
      !!draft &&
      (draft.slot !== brand.slot ||
        draft.tier !== brand.tier ||
        draft.description !== brand.description)
    );
  };

  const save = async (brand: ProviderBrand) => {
    const draft = drafts[brand.id];
    if (!draft) return;
    setBusyId(brand.id);
    setError(null);
    try {
      const updated = await adminService.updateProviderBrand(brand.id, draft);
      setBrands((prev) => prev?.map((b) => (b.id === brand.id ? updated : b)) ?? null);
      setSavedId(brand.id);
      window.setTimeout(() => setSavedId(null), 2000);
    } catch {
      setError('Could not save. Please try again.');
    } finally {
      setBusyId(null);
    }
  };

  const edit = (id: string, patch: Partial<Draft>) =>
    setDrafts((d) => {
      const current = d[id];
      return current ? { ...d, [id]: { ...current, ...patch } } : d;
    });

  if (brands === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        These are the names customers see. The underlying provider is never shown to them, so you can
        rename a slot or move it to a different provider without anything changing on their side.
        Changes reach users on their next page load.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {brands.map((brand) => {
        const draft = drafts[brand.id] ?? { slot: '', tier: '', description: '' };
        return (
          <Card key={brand.id}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-baseline gap-2 text-base">
                <span>
                  {draft.slot || '—'} · {draft.tier || '—'}
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  currently served by {brand.provider}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor={`slot-${brand.id}`}>Name</Label>
                  <Input
                    id={`slot-${brand.id}`}
                    value={draft.slot}
                    maxLength={50}
                    placeholder="Model 1"
                    onChange={(e) => edit(brand.id, { slot: e.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`tier-${brand.id}`}>Tier</Label>
                  <Input
                    id={`tier-${brand.id}`}
                    value={draft.tier}
                    maxLength={50}
                    placeholder="Standard"
                    onChange={(e) => edit(brand.id, { tier: e.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`desc-${brand.id}`}>Description</Label>
                <Textarea
                  id={`desc-${brand.id}`}
                  value={draft.description}
                  maxLength={255}
                  rows={2}
                  placeholder="Shown as a tooltip when a customer picks this model."
                  onChange={(e) => edit(brand.id, { description: e.target.value })}
                />
              </div>
              <div className="flex items-center gap-3">
                <Button size="sm" disabled={!isDirty(brand) || busyId === brand.id} onClick={() => void save(brand)}>
                  {busyId === brand.id ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
                  Save
                </Button>
                {savedId === brand.id && <span className="text-xs text-muted-foreground">Saved</span>}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
