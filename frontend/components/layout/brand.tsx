import Link from 'next/link';

import { cn } from '@/lib/utils';

/**
 * The product mark.
 *
 * A glyph rather than an imported asset so it inherits the theme and stays sharp at any size, and
 * one component rather than a copy in each header — the nav, the sidebar and the marketing page all
 * showed a slightly different lockup before.
 */
export function Brand({
  href = '/chat',
  className,
  showWordmark = true,
}: {
  href?: string;
  className?: string;
  showWordmark?: boolean;
}) {
  return (
    <Link href={href} className={cn('flex items-center gap-2', className)} aria-label="ai.sumitgroups">
      <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-primary text-primary-foreground shadow-sm">
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="currentColor" aria-hidden>
          {/* Two overlapping sparks: one prompt, two models. */}
          <path d="M9 3l1.4 3.6L14 8l-3.6 1.4L9 13l-1.4-3.6L4 8l3.6-1.4L9 3z" />
          <path d="M16.5 12l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1 1-2.5z" opacity=".75" />
        </svg>
      </span>
      {showWordmark && (
        <span className="text-[15px] font-semibold tracking-tight">
          ai<span className="text-muted-foreground">.</span>sumitgroups
        </span>
      )}
    </Link>
  );
}
