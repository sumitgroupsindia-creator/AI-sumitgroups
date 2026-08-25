'use client';

import Link from 'next/link';
import { ArrowRight, Columns2, Gauge, History, ImageUp, Layers, Shield, Sparkles, Zap } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PricingTable } from '@/features/billing/pricing-table';
import { useAuth } from '@/features/auth/auth-provider';

const FEATURES = [
  {
    icon: Columns2,
    title: 'Side-by-side comparison',
    description:
      'Every image prompt runs through two independent models at once. Both results land in the same view, labelled Model 1 and Model 2.',
  },
  {
    icon: Zap,
    title: 'Truly parallel, never sequential',
    description:
      'Providers are called concurrently. Whichever finishes first renders immediately — you never wait for the slower one.',
  },
  {
    icon: Shield,
    title: 'Resilient to provider failures',
    description:
      'If one model errors or times out, the other still delivers. Failed generations are refunded, never silently charged.',
  },
  {
    icon: ImageUp,
    title: 'Bring your own photo',
    description:
      'Upload a JPG, PNG or WEBP and use it as the starting point for generation and editing, where the model supports it.',
  },
  {
    icon: History,
    title: 'Everything is saved',
    description:
      'Chats and generated images are kept in your history, private to your account and downloadable any time.',
  },
  {
    icon: Gauge,
    title: 'Transparent credits',
    description:
      'See exactly what each operation cost, per provider and per model, with a full usage log in settings.',
  },
];

const STEPS = [
  { title: 'Write one prompt', description: 'Describe the image you want, or paste in a photo to work from.' },
  { title: 'Pick your models', description: 'Run Model 1, Model 2, or both at the same time.' },
  { title: 'Compare and choose', description: 'Two results, one view. Download or regenerate either side.' },
];

const FAQS = [
  {
    q: 'Which models does the platform use?',
    a: 'Model 1 (Standard) and Model 2 (Premium) are two independent, industry-leading AI engines. We select and tune them for you, and can upgrade either one without you changing anything in your workflow.',
  },
  {
    q: 'What happens if one provider fails?',
    a: 'Nothing blocks. Each provider has its own result card with its own status. A failure shows a retry button on that card only, and the credits reserved for the failed call are returned to your balance.',
  },
  {
    q: 'How do credits work?',
    a: 'Each AI operation consumes credits from your monthly allowance — chat credits for messages, image credits per provider per image. Your plan sets the allowance, and every deduction is listed in Settings → Usage.',
  },
  {
    q: 'Can I use my own photos?',
    a: 'Yes. Upload a JPG, PNG or WEBP up to your plan limit and it becomes the input for generation or editing on models that accept image input. Uploads are private and served only to you through authenticated endpoints.',
  },
  {
    q: 'Is my data private to me?',
    a: 'Yes. Conversations, uploads and generated images are scoped to your account. Files are served through authenticated APIs that verify ownership on every request.',
  },
  {
    q: 'How do I pay, and can I cancel?',
    a: 'Payments are processed by Razorpay; we never handle your card details. You can cancel any time from Settings → Subscription and you keep access until the end of the period you have paid for.',
  },
];

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
        <div className="container flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Sparkles className="h-5 w-5" />
            ai.sumitgroups
          </Link>
          <nav className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="#features">Features</Link>
            </Button>
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="#pricing">Pricing</Link>
            </Button>
            {user ? (
              <Button asChild size="sm">
                <Link href="/chat">Open app</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild size="sm">
                  <Link href="/signup">Get started</Link>
                </Button>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="container py-20 text-center sm:py-28">
          <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl">
            One Prompt. Multiple AI Models. Better Results.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
            Stop guessing which model handles your prompt best. Run it through two advanced AI models
            simultaneously and compare both results side by side.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="gap-2">
              <Link href={user ? '/images' : '/signup'}>
                {user ? 'Open Image Studio' : 'Start free'}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="#how-it-works">See how it works</Link>
            </Button>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">Free plan included. No card required.</p>

          <ComparisonDemo />
        </section>

        {/* Features */}
        <section id="features" className="border-t bg-muted/30 py-20">
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-semibold tracking-tight">Built for comparing, not just generating</h2>
              <p className="mt-3 text-muted-foreground">
                Every part of the product is designed around running more than one model at a time.
              </p>
            </div>
            <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature) => {
                const Icon = feature.icon;
                return (
                  <Card key={feature.title}>
                    <CardHeader>
                      <Icon className="h-5 w-5" />
                      <CardTitle className="pt-2 text-base">{feature.title}</CardTitle>
                      <CardDescription>{feature.description}</CardDescription>
                    </CardHeader>
                  </Card>
                );
              })}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="py-20">
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-semibold tracking-tight">How it works</h2>
            </div>
            <div className="mt-12 grid gap-8 md:grid-cols-3">
              {STEPS.map((step, index) => (
                <div key={step.title}>
                  <div className="flex h-9 w-9 items-center justify-center rounded-full border text-sm font-medium">
                    {index + 1}
                  </div>
                  <h3 className="mt-4 font-medium">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{step.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="border-t bg-muted/30 py-20">
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-semibold tracking-tight">Pricing</h2>
              <p className="mt-3 text-muted-foreground">Start free. Upgrade when you need more credits.</p>
            </div>
            <div className="mt-12">
              <PricingTable />
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="py-20">
          <div className="container max-w-3xl">
            <h2 className="text-center text-3xl font-semibold tracking-tight">Frequently asked questions</h2>
            <div className="mt-10 divide-y rounded-xl border">
              {FAQS.map((faq) => (
                <details key={faq.q} className="group p-5">
                  <summary className="cursor-pointer list-none font-medium marker:hidden">
                    <span className="flex items-center justify-between gap-4">
                      {faq.q}
                      <span className="text-muted-foreground transition-transform group-open:rotate-45">+</span>
                    </span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{faq.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="border-t py-20">
          <div className="container text-center">
            <Layers className="mx-auto h-8 w-8" />
            <h2 className="mt-4 text-3xl font-semibold tracking-tight">Ready to compare?</h2>
            <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
              Write one prompt and see what two of the best models each make of it.
            </p>
            <Button asChild size="lg" className="mt-8 gap-2">
              <Link href={user ? '/images' : '/signup'}>
                {user ? 'Open Image Studio' : 'Create your free account'}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t py-10">
        <div className="container flex flex-col items-center justify-between gap-4 text-sm text-muted-foreground sm:flex-row">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            <span>ai.sumitgroups.com</span>
          </div>
          <nav className="flex gap-6">
            <Link href="/pricing" className="hover:text-foreground">
              Pricing
            </Link>
            <Link href="/login" className="hover:text-foreground">
              Sign in
            </Link>
            <Link href="/signup" className="hover:text-foreground">
              Sign up
            </Link>
          </nav>
          <p>© {new Date().getFullYear()} Sumit Groups</p>
        </div>
      </footer>
    </div>
  );
}

/** Static illustration of the two-model layout — no fabricated sample outputs, just the structure. */
function ComparisonDemo() {
  return (
    <div className="mx-auto mt-16 max-w-4xl">
      <div className="rounded-xl border bg-card p-4 text-left shadow-sm">
        <div className="rounded-lg bg-muted/60 px-4 py-3 text-sm text-muted-foreground">
          Create a professional cinematic portrait, dramatic side lighting, shallow depth of field…
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {[
            { slot: 'Model 1', tier: 'Standard' },
            { slot: 'Model 2', tier: 'Premium' },
          ].map((model) => (
            <div key={model.slot} className="overflow-hidden rounded-lg border">
              <div className="flex items-center justify-between border-b px-3 py-2">
                <span className="text-sm font-medium">{model.slot}</span>
                <span className="rounded-full border px-2 py-0.5 text-[10px] text-muted-foreground">
                  {model.tier}
                </span>
              </div>
              <div className="flex aspect-square items-center justify-center bg-gradient-to-br from-muted/80 to-muted/30">
                <Sparkles className="h-6 w-6 text-muted-foreground/40" />
              </div>
              <div className="flex gap-2 border-t px-3 py-2 text-xs text-muted-foreground">
                <span>Download</span>
                <span>·</span>
                <span>Regenerate</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
