'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { formatDate } from '@/lib/utils';
import * as adminService from '@/services/admin.service';
import type { AdminUser } from '@/types/api';

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    void adminService.listUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  const patch = async (id: string, changes: { is_active?: boolean; is_admin?: boolean }) => {
    setBusyId(id);
    try {
      const updated = await adminService.updateUser(id, changes);
      setUsers((prev) => prev?.map((u) => (u.id === id ? updated : u)) ?? null);
    } finally {
      setBusyId(null);
    }
  };

  if (users === null) return <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />;

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-3 font-medium">User</th>
            <th className="px-4 py-3 font-medium">Joined</th>
            <th className="px-4 py-3 font-medium">Active</th>
            <th className="px-4 py-3 font-medium">Admin</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} className="border-t">
              <td className="px-4 py-3">
                <p className="font-medium">{user.full_name || '—'}</p>
                <p className="text-xs text-muted-foreground">{user.email}</p>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatDate(user.created_at)}</td>
              <td className="px-4 py-3">
                <Switch
                  checked={user.is_active}
                  disabled={busyId === user.id}
                  onCheckedChange={(checked) => void patch(user.id, { is_active: checked })}
                />
              </td>
              <td className="px-4 py-3">
                {user.is_admin ? <Badge>Admin</Badge> : <Badge variant="secondary">User</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
