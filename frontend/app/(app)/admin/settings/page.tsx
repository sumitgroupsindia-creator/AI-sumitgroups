'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import * as adminService from '@/services/admin.service';
import type { AdminSetting, AdminSettingAudit } from '@/types/api';

/** Order the groups deliberately rather than however the API happened to list them. */
const GROUP_ORDER = ['AI providers', 'Payments', 'Email', 'Uploads', 'Rate limiting'];

function isTruthy(value: string) {
  return ['1', 'true', 'yes', 'on'].includes(value.trim().toLowerCase());
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSetting[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedKeys, setSavedKeys] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AdminSettingAudit[] | null>(null);
  const [showAudit, setShowAudit] = useState(false);

  const load = () =>
    adminService
      .listSettings()
      .then((items) => {
        setSettings(items);
        // Secrets start blank: the server never sends them back, and blank means "leave alone".
        setDrafts(Object.fromEntries(items.map((s) => [s.key, s.is_secret ? '' : s.value])));
      })
      .catch(() => setSettings([]));

  useEffect(() => {
    void load();
  }, []);

  const changed = useMemo(() => {
    if (!settings) return [] as string[];
    return settings
      .filter((s) => {
        const draft = drafts[s.key] ?? '';
        // A blank secret is an untouched field, not a request to clear it.
        if (s.is_secret) return draft.length > 0;
        return draft !== s.value;
      })
      .map((s) => s.key);
  }, [settings, drafts]);

  const save = async () => {
    if (changed.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const payload = Object.fromEntries(changed.map((key) => [key, drafts[key] ?? '']));
      const updated = await adminService.updateSettings(payload);
      setSettings(updated);
      setDrafts(Object.fromEntries(updated.map((s) => [s.key, s.is_secret ? '' : s.value])));
      setSavedKeys(changed);
      window.setTimeout(() => setSavedKeys(null), 3000);
      if (showAudit) void adminService.listSettingAudit().then(setAudit);
    } catch {
      setError('Could not save. Check the values and try again.');
    } finally {
      setSaving(false);
    }
  };

  const toggleAudit = () => {
    const next = !showAudit;
    setShowAudit(next);
    if (next && audit === null) void adminService.listSettingAudit().then(setAudit).catch(() => setAudit([]));
  };

  if (settings === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  const groups = GROUP_ORDER.filter((g) => settings.some((s) => s.group === g)).concat(
    [...new Set(settings.map((s) => s.group))].filter((g) => !GROUP_ORDER.includes(g)),
  );

  return (
    <div className="space-y-6 pb-24">
      <p className="text-sm text-muted-foreground">
        These override the matching entries in the server&apos;s <code>.env</code> file and take
        effect within about 15 seconds — no restart, no deploy. Infrastructure that the app needs
        before it can reach the database (database URL, Redis, JWT secret) is deliberately not listed
        here and still lives in <code>.env</code>.
      </p>

      {groups.map((group) => (
        <Card key={group}>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{group}</CardTitle>
            {group === 'AI providers' && (
              <CardDescription>
                Keys are encrypted before they are stored and are never shown again after saving.
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-5">
            {settings
              .filter((s) => s.group === group)
              .map((setting) => {
                const draft = drafts[setting.key] ?? '';
                const dirty = changed.includes(setting.key);
                return (
                  <div key={setting.key} className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Label htmlFor={setting.key}>{setting.label}</Label>
                      {setting.source === 'database' ? (
                        <Badge variant="outline" className="text-[10px]">
                          set here
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-muted-foreground">
                          from .env
                        </Badge>
                      )}
                      {dirty && <span className="text-[10px] text-muted-foreground">unsaved</span>}
                      {savedKeys?.includes(setting.key) && (
                        <span className="text-[10px] text-muted-foreground">saved</span>
                      )}
                    </div>

                    {setting.unreadable && (
                      <p className="flex items-start gap-1.5 text-xs text-destructive">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                        Stored value cannot be decrypted with the current encryption key. Enter it
                        again to replace it.
                      </p>
                    )}

                    {setting.kind === 'bool' ? (
                      <div className="flex items-center gap-2">
                        <Switch
                          id={setting.key}
                          checked={isTruthy(draft)}
                          onCheckedChange={(checked) =>
                            setDrafts((d) => ({ ...d, [setting.key]: checked ? 'true' : 'false' }))
                          }
                        />
                        <span className="text-xs text-muted-foreground">
                          {isTruthy(draft) ? 'On' : 'Off'}
                        </span>
                      </div>
                    ) : setting.kind === 'select' ? (
                      <select
                        id={setting.key}
                        value={draft}
                        onChange={(e) => setDrafts((d) => ({ ...d, [setting.key]: e.target.value }))}
                        className={cn(
                          'flex h-9 w-full max-w-sm rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm',
                          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                        )}
                      >
                        {setting.options.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        id={setting.key}
                        className="max-w-sm"
                        type={setting.kind === 'int' ? 'number' : setting.is_secret ? 'password' : 'text'}
                        autoComplete={setting.is_secret ? 'new-password' : 'off'}
                        value={draft}
                        placeholder={
                          setting.is_secret
                            ? setting.is_set
                              ? `${setting.masked} — leave blank to keep`
                              : 'Not set'
                            : ''
                        }
                        onChange={(e) => setDrafts((d) => ({ ...d, [setting.key]: e.target.value }))}
                      />
                    )}

                    {setting.help && <p className="text-xs text-muted-foreground">{setting.help}</p>}
                  </div>
                );
              })}
          </CardContent>
        </Card>
      ))}

      <div>
        <Button variant="ghost" size="sm" onClick={toggleAudit}>
          {showAudit ? 'Hide' : 'Show'} change history
        </Button>
        {showAudit && (
          <Card className="mt-3">
            <CardContent className="pt-6">
              {audit === null ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              ) : audit.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing has been changed yet.</p>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-muted-foreground">
                    <tr className="border-b">
                      <th className="pb-2 pr-4 font-medium">Setting</th>
                      <th className="pb-2 pr-4 font-medium">Changed to</th>
                      <th className="pb-2 pr-4 font-medium">By</th>
                      <th className="pb-2 font-medium">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((entry) => (
                      <tr key={entry.id} className="border-b last:border-0">
                        <td className="py-2.5 pr-4 font-mono text-xs">{entry.key}</td>
                        <td className="py-2.5 pr-4 font-mono text-xs">{entry.new_preview || '—'}</td>
                        <td className="py-2.5 pr-4 text-muted-foreground">{entry.actor_email}</td>
                        <td className="py-2.5 text-muted-foreground">
                          {new Date(entry.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Sticky so the save action stays reachable on a long form. */}
      <div className="fixed inset-x-0 bottom-0 border-t bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <span className="text-xs text-muted-foreground">
            {error ? (
              <span className="text-destructive">{error}</span>
            ) : changed.length === 0 ? (
              'No unsaved changes'
            ) : (
              `${changed.length} unsaved change${changed.length === 1 ? '' : 's'}`
            )}
          </span>
          <Button size="sm" disabled={changed.length === 0 || saving} onClick={() => void save()}>
            {saving && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            Save changes
          </Button>
        </div>
      </div>
    </div>
  );
}
