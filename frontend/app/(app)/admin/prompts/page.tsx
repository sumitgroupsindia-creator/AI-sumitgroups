'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import * as adminService from '@/services/admin.service';
import type { PromptTemplate } from '@/types/api';

type Draft = Pick<PromptTemplate, 'name' | 'description' | 'content'>;

const KIND_BLURB: Record<PromptTemplate['kind'], string> = {
  base: 'Always applied.',
  task: 'Applied when the router decides this fits the request.',
  tool: 'Run by the app itself. Switching it off skips the step and the API call it costs.',
};

function draftOf(template: PromptTemplate): Draft {
  return { name: template.name, description: template.description, content: template.content };
}

export default function AdminPromptsPage() {
  const [templates, setTemplates] = useState<PromptTemplate[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void adminService
      .listPromptTemplates()
      .then((items) => {
        setTemplates(items);
        setDrafts(Object.fromEntries(items.map((t) => [t.id, draftOf(t)])));
      })
      .catch(() => setTemplates([]));
  }, []);

  const isDirty = (template: PromptTemplate) => {
    const draft = drafts[template.id];
    if (!draft) return false;
    const saved = draftOf(template);
    return (Object.keys(saved) as (keyof Draft)[]).some((key) => draft[key] !== saved[key]);
  };

  const patch = async (id: string, changes: Partial<Draft> & { is_enabled?: boolean }) => {
    setBusyId(id);
    setError(null);
    try {
      const updated = await adminService.updatePromptTemplate(id, changes);
      setTemplates((prev) => prev?.map((t) => (t.id === id ? updated : t)) ?? null);
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

  if (templates === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        What the product tells the model before the customer&apos;s own words reach it. Every request
        gets the <span className="font-medium text-foreground">base</span> prompt for its mode; one{' '}
        <span className="font-medium text-foreground">task</span> prompt may be added on top when the
        router judges it a fit. Changes take effect on the next request — no deploy.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {templates.map((template) => {
        const draft = drafts[template.id];
        if (!draft) return null;

        return (
          <div
            key={template.id}
            className={cn('rounded-lg border p-4', !template.is_enabled && 'opacity-60')}
          >
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="capitalize">
                {template.scope}
              </Badge>
              <Badge variant="secondary" className="capitalize">
                {template.kind}
              </Badge>
              <code className="text-xs text-muted-foreground">{template.key}</code>
              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {template.is_enabled ? 'On' : 'Off'}
                </span>
                <Switch
                  checked={template.is_enabled}
                  disabled={busyId === template.id}
                  onCheckedChange={(checked) => void patch(template.id, { is_enabled: checked })}
                />
              </div>
            </div>

            <p className="mb-3 text-xs text-muted-foreground">{KIND_BLURB[template.kind]}</p>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor={`name-${template.id}`} className="text-xs">
                  Name
                </Label>
                <Input
                  id={`name-${template.id}`}
                  className="h-8"
                  value={draft.name}
                  maxLength={100}
                  onChange={(e) => edit(template.id, { name: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor={`desc-${template.id}`} className="text-xs">
                  When to use it
                </Label>
                <Textarea
                  id={`desc-${template.id}`}
                  className="min-h-16 text-xs"
                  value={draft.description}
                  maxLength={500}
                  onChange={(e) => edit(template.id, { description: e.target.value })}
                />
                {template.kind === 'task' && (
                  <p className="text-[11px] text-muted-foreground">
                    The router reads this to decide whether the template fits a request, so it
                    changes behaviour — not just what this screen says.
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor={`content-${template.id}`} className="text-xs">
                  Prompt
                </Label>
                <Textarea
                  id={`content-${template.id}`}
                  className="min-h-48 font-mono text-xs leading-relaxed"
                  value={draft.content}
                  onChange={(e) => edit(template.id, { content: e.target.value })}
                />
              </div>
            </div>

            {isDirty(template) && (
              <Button
                size="sm"
                className="mt-3"
                disabled={busyId === template.id}
                onClick={() => void patch(template.id, draft)}
              >
                {busyId === template.id && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                Save
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
