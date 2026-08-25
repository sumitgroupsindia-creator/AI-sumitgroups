'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/features/auth/auth-provider';
import { ApiError } from '@/lib/api-client';
import * as authService from '@/services/auth.service';

export default function ProfileSettingsPage() {
  const { user, refreshUser } = useAuth();
  const [fullName, setFullName] = useState('');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFullName(user?.full_name ?? '');
  }, [user]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('saving');
    setError(null);
    try {
      await authService.updateProfile(fullName);
      await refreshUser();
      setStatus('saved');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your profile.');
      setStatus('idle');
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Update how your name appears in the app.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" value={user?.email ?? ''} disabled />
            <p className="text-xs text-muted-foreground">Your email address cannot be changed here.</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="fullName">Name</Label>
            <Input id="fullName" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" className="gap-2" disabled={status === 'saving'}>
              {status === 'saving' && <Loader2 className="h-4 w-4 animate-spin" />}
              Save changes
            </Button>
            {status === 'saved' && <span className="text-sm text-muted-foreground">Saved.</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
