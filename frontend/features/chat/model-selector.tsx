'use client';

import { useModelLabel } from '@/features/branding/model-branding';
import { cn } from '@/lib/utils';
import type { ProviderName } from '@/types/api';

const OPTIONS: ProviderName[] = ['openai', 'gemini'];

interface ModelSelectorProps {
  value: ProviderName;
  onChange: (value: ProviderName) => void;
  disabled?: boolean;
}

export function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  const labelFor = useModelLabel();

  return (
    <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label="Model">
      {OPTIONS.map((option) => {
        const label = labelFor(option);
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={value === option}
            aria-label={`${label.slot}, ${label.tier}`}
            title={label.description}
            disabled={disabled}
            onClick={() => onChange(option)}
            className={cn(
              'rounded px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50',
              value === option ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {label.slot}
          </button>
        );
      })}
    </div>
  );
}
