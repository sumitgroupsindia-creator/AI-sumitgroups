'use client';

import { useRef, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { ChevronDown, ImageIcon, Loader2, Lock, Paperclip, Plus, Send, Square, X } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useModelLabel, useModelLabels } from '@/features/branding/model-branding';
import { modelName } from '@/lib/model-labels';
import { useIsPaid } from '@/hooks/use-entitlement';
import { cn } from '@/lib/utils';
import type { ComposerMode, ModelSelection, ProviderName } from '@/types/api';

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export interface Attachment {
  file: File;
  previewUrl: string;
}

/**
 * The prompt box, and everything a turn is configured with.
 *
 * One control opens everything that is not typing — attaching a photo, switching the turn to an
 * image — because a composer that grows a button per capability runs out of room by the fourth one.
 * The menu carries only what the product can actually do; an entry that opens nothing is worse than
 * an entry that is missing.
 */
export function PromptBox({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  mode,
  onModeChange,
  selection,
  onSelectionChange,
  attachment,
  onPickFile,
  onClearAttachment,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  busy: boolean;
  mode: ComposerMode;
  onModeChange: (mode: ComposerMode) => void;
  selection: ModelSelection;
  onSelectionChange: (selection: ModelSelection) => void;
  attachment: Attachment | null;
  onPickFile: (file: File | undefined) => void;
  onClearAttachment: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const labels = useModelLabels();
  const labelFor = useModelLabel();
  const { isPaid } = useIsPaid();
  const providers = Object.keys(labels) as ProviderName[];

  // A slot is locked when it needs a paid plan and this account has not got one. "Both" is locked
  // whenever any slot in it is — the same rule as the server's, stated once.
  const isLocked = (provider: ProviderName) =>
    Boolean(labelFor(provider).requiresPaidPlan) && !isPaid;
  const bothLocked = providers.some(isLocked);

  const selectionLabel =
    selection === 'both' ? 'दोनों' : modelName(labelFor(selection));

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="w-full">
      {attachment && (
        <div className="mx-auto mb-2 flex max-w-[720px] items-center gap-2.5 rounded-xl border border-border/70 bg-card px-2.5 py-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL, never remote */}
          <img src={attachment.previewUrl} alt="" className="h-10 w-10 rounded-lg object-cover" />
          <span className="flex-1 truncate text-xs text-muted-foreground">{attachment.file.name}</span>
          <button
            type="button"
            onClick={onClearAttachment}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="हटाओ"
          >
            <X className="h-3.5 w-3.5" />
            <span className="sr-only">तस्वीर हटाओ</span>
          </button>
        </div>
      )}

      <div
        className={cn(
          'mx-auto flex max-w-[720px] items-end gap-1.5 rounded-[26px] border border-border/70 bg-card p-1.5 pl-2 transition-shadow',
          'focus-within:border-ring/60 focus-within:shadow-lg focus-within:shadow-primary/5',
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          className="hidden"
          onChange={(e) => {
            onPickFile(e.target.files?.[0]);
            e.target.value = ''; // so picking the same file twice still fires a change
          }}
        />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={busy}
              title="और विकल्प"
              className="mb-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50 data-[state=open]:bg-accent data-[state=open]:text-foreground"
            >
              <Plus className="h-[18px] w-[18px]" />
              <span className="sr-only">और विकल्प</span>
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="start" className="w-[17rem]">
            <DropdownMenuItem onSelect={() => fileInputRef.current?.click()}>
              <Paperclip className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="font-medium">फ़ोटो या फ़ाइल लगाओ</p>
                <p className="text-[11px] leading-snug text-muted-foreground">
                  JPG, PNG या WEBP — उसी के बारे में पूछो या उसे बदलवाओ
                </p>
              </div>
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuCheckboxItem
              checked={mode === 'image'}
              onCheckedChange={(checked) => onModeChange(checked ? 'image' : 'chat')}
            >
              <ImageIcon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="font-medium">तस्वीर बनाओ</p>
                <p className="text-[11px] leading-snug text-muted-foreground">
                  जवाब शब्दों में नहीं, तस्वीर में आएगा
                </p>
              </div>
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={busy}
          placeholder={
            mode === 'image'
              ? 'कैसी तस्वीर चाहिए, लिखो…'
              : 'क्या लिखवाना है? फ़ोटो भी लगा सकते हो…'
          }
          className="max-h-44 min-h-[38px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-6 outline-none placeholder:text-muted-foreground disabled:opacity-60"
        />

        <div className="mb-0.5 flex shrink-0 items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                disabled={busy}
                title="कौन सा मॉडल"
                className="inline-flex h-9 items-center gap-1 rounded-full px-2.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50 data-[state=open]:bg-accent"
              >
                <span className="max-w-[92px] truncate">{selectionLabel}</span>
                <ChevronDown className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-[15rem]">
              <DropdownMenuLabel>मॉडल चुनो</DropdownMenuLabel>
              {providers.map((provider) => (
                <SlotOption
                  key={provider}
                  checked={selection === provider}
                  locked={isLocked(provider)}
                  title={modelName(labelFor(provider))}
                  body={labelFor(provider).description}
                  onPick={() => onSelectionChange(provider)}
                />
              ))}
              <DropdownMenuSeparator />
              <SlotOption
                checked={selection === 'both'}
                locked={bothLocked}
                title="दोनों"
                body="दोनों से एक साथ पूछो और जवाब साथ-साथ देखो"
                onPick={() => onSelectionChange('both')}
              />
            </DropdownMenuContent>
          </DropdownMenu>

          {busy ? (
            <button
              type="button"
              onClick={onStop}
              title="रोको"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-secondary text-secondary-foreground transition-opacity hover:opacity-90"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              <span className="sr-only">रोको</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={onSubmit}
              disabled={!value.trim()}
              title="भेजो"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
              <span className="sr-only">भेजो</span>
            </button>
          )}
        </div>
      </div>

    </div>
  );
}

/**
 * One choice in the model menu, locked or not.
 *
 * A locked slot is shown rather than hidden: someone on the free plan should be able to see what
 * they are not getting and how to get it. It is not selectable, so nobody types a prompt against a
 * slot the server will refuse.
 */
function SlotOption({
  checked,
  locked,
  title,
  body,
  onPick,
}: {
  checked: boolean;
  locked: boolean;
  title: string;
  body: string;
  onPick: () => void;
}) {
  if (locked) {
    return (
      <Link
        href="/pricing"
        className="flex cursor-pointer select-none items-start gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors hover:bg-accent"
      >
        <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="font-medium text-muted-foreground">{title}</p>
          <p className="text-[11px] leading-snug text-primary">
            पेड प्लान चाहिए — अपग्रेड करो
          </p>
        </div>
      </Link>
    );
  }

  return (
    <DropdownMenuCheckboxItem checked={checked} onCheckedChange={onPick}>
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        <p className="text-[11px] leading-snug text-muted-foreground">{body}</p>
      </div>
    </DropdownMenuCheckboxItem>
  );
}

/** A quick-start chip below the composer. */
export function ComposerChip({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  label: string;
  icon?: typeof ImageIcon;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] transition-colors',
        active
          ? 'border-primary/40 bg-primary/10 text-primary'
          : 'border-border/70 bg-card text-muted-foreground hover:bg-accent hover:text-foreground',
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" />}
      <span className="max-w-[260px] truncate">{label}</span>
    </button>
  );
}

export { Loader2 };
