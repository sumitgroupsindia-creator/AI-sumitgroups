'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import * as adminService from '@/services/admin.service';
import type { Plan } from '@/types/api';

type Draft = { monthly_credits: number; price: number };

export default function AdminPlansPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    void adminService
      .listPlans()
      .then((items) => {
        setPlans(items);
        setDrafts(
          Object.fromEntries(
            items.map((p) => [
              p.id,
              { monthly_credits: p.monthly_credits, price: Number.parseFloat(p.price) },
            ]),
          ),
        );
      })
      .catch(() => setPlans([]));
  }, []);

  const save = async (plan: Plan) => {
    const draft = drafts[plan.id];
    if (!draft) return;
    setBusyId(plan.id);
    try {
      const updated = await adminService.updatePlan(plan.id, draft);
      setPlans((prev) => prev?.map((p) => (p.id === plan.id ? updated : p)) ?? null);
    } finally {
      setBusyId(null);
    }
  };

  if (plans === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Plan limits and pricing are read from the database at runtime — the frontend never hard-codes
        them. One credit is one rupee, so an allowance that matches the price keeps that promise
        literally true; granting more credits than the plan costs spends the margin set on the{' '}
        <span className="font-medium text-foreground">Pricing</span> tab.
      </p>
      {plans.map((plan) => {
        const draft = drafts[plan.id];
        if (!draft) return null;
        const update = (patch: Partial<Draft>) =>
          setDrafts((d) => ({ ...d, [plan.id]: { ...draft, ...patch } }));

        return (
          <Card key={plan.id}>
            <CardHeader>
              <CardTitle className="text-base">
                {plan.name} <span className="text-xs font-normal text-muted-foreground">({plan.code})</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`price-${plan.id}`} className="text-xs">
                    Price ({plan.currency})
                  </Label>
                  <Input
                    id={`price-${plan.id}`}
                    type="number"
                    min={0}
                    value={draft.price}
                    onChange={(e) => update({ price: Number(e.target.value) })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`credits-${plan.id}`} className="text-xs">
                    Monthly credits
                  </Label>
                  <Input
                    id={`credits-${plan.id}`}
                    type="number"
                    min={0}
                    value={draft.monthly_credits}
                    onChange={(e) => update({ monthly_credits: Number(e.target.value) })}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    ₹{draft.monthly_credits.toLocaleString()} of usage
                  </p>
                </div>
                <div className="flex items-end">
                  <Button className="w-full" disabled={busyId === plan.id} onClick={() => void save(plan)}>
                    Save
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
