'use client';

import { ImageIcon, MessageSquare } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { ComposerMode } from '@/types/api';

// English, while the prompts and starters stay Hindi: the labels name the two things the product
// does, and those read the same on every screen and in the admin console.
const MODES: { value: ComposerMode; label: string; icon: typeof MessageSquare }[] = [
  { value: 'chat', label: 'Chat', icon: MessageSquare },
  { value: 'image', label: 'Image', icon: ImageIcon },
];

/**
 * Whether the next turn asks for words or for a picture.
 *
 * One control rather than two destinations: the same prompt box, the same thread and the same model
 * slots serve both, so sending the user to a separate screen for images only split the work in two.
 */
export function ModeToggle({
  value,
  onChange,
  size = 'md',
}: {
  value: ComposerMode;
  onChange: (mode: ComposerMode) => void;
  size?: 'sm' | 'md';
}) {
  return (
    <div
      className={cn('inline-flex rounded-full border bg-card p-1', size === 'sm' && 'p-0.5')}
      role="radiogroup"
      aria-label="Chat or image"
    >
      {MODES.map(({ value: mode, label, icon: Icon }) => (
        <button
          key={mode}
          type="button"
          role="radio"
          aria-checked={value === mode}
          onClick={() => onChange(mode)}
          className={cn(
            'flex items-center gap-1.5 rounded-full font-medium transition-colors',
            size === 'sm' ? 'px-3 py-1 text-xs' : 'px-4 py-1.5 text-sm',
            value === mode
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Icon className={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
          {label}
        </button>
      ))}
    </div>
  );
}
