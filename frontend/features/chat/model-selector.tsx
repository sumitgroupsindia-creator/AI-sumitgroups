'use client';

import { cn } from '@/lib/utils';
import type { ProviderName } from '@/types/api';

const OPTIONS: { value: ProviderName; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'gemini', label: 'Gemini' },
];

interface ModelSelectorProps {
  value: ProviderName;
  onChange: (value: ProviderName) => void;
  disabled?: boolean;
}

export function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  return (
    <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label="Model">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
            value === option.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
