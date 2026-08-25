'use client';

import { useModelLabel, useModelLabels } from '@/features/branding/model-branding';
import { cn } from '@/lib/utils';
import type { ModelSelection, ProviderName } from '@/types/api';

/**
 * Picks one model slot or both. Shared by chat and image so the choice means the same thing in
 * either mode, and reads its labels from branding rather than hard-coding "Model 1".
 */
export function SlotSelector({
  value,
  onChange,
  disabled,
}: {
  value: ModelSelection;
  onChange: (value: ModelSelection) => void;
  disabled?: boolean;
}) {
  const labels = useModelLabels();
  const labelFor = useModelLabel();
  const providers = Object.keys(labels) as ProviderName[];

  const options: { value: ModelSelection; label: string; title: string }[] = [
    ...providers.map((provider) => ({
      value: provider as ModelSelection,
      label: labelFor(provider).tier,
      title: `${labelFor(provider).slot} — ${labelFor(provider).description}`,
    })),
    { value: 'both', label: 'दोनों', title: 'दोनों मॉडल से एक साथ जवाब लो और तुलना करो' },
  ];

  return (
    <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label="मॉडल चुनो">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          title={option.title}
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

/** The concrete slots a selection resolves to. */
export function providersFor(selection: ModelSelection, known: ProviderName[]): ProviderName[] {
  return selection === 'both' ? known : [selection];
}
