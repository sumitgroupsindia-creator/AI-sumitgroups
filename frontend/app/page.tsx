'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  Columns2,
  Gauge,
  History,
  ImageIcon,
  ImageUp,
  Layers,
  MessageSquare,
  Paperclip,
  Shield,
  Sparkles,
  Zap,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PricingTable } from '@/features/billing/pricing-table';
import { Brand } from '@/components/layout/brand';
import { ThemeToggle } from '@/features/theme/theme-provider';
import { useAuth } from '@/features/auth/auth-provider';

/**
 * The tools, and only the tools that exist.
 *
 * A landing page is a promise. Listing a generator the product does not have wins one click and
 * loses the visitor at the moment they press it, so this grid is kept honest against the app.
 */
const TOOLS = [
  {
    href: '/chat',
    icon: MessageSquare,
    title: 'AI Chat',
    body: 'कैप्शन, पोस्ट, स्क्रिप्ट, जवाब — हिंदी में भी, अंग्रेज़ी में भी।',
  },
  {
    href: '/images',
    icon: ImageIcon,
    title: 'AI Image Generator',
    body: 'लिखो और तस्वीर बनवाओ — पोस्टर, बैनर, प्रोडक्ट फ़ोटो।',
  },
  {
    href: '/images',
    icon: Paperclip,
    title: 'Photo से बनाओ',
    body: 'अपनी फ़ोटो लगाओ और उसी को स्टूडियो जैसा बदलवाओ।',
  },
  {
    href: '/chat',
    icon: Columns2,
    title: 'दो मॉडल, साथ-साथ',
    body: 'एक ही प्रॉम्प्ट दो मॉडल को — दोनों जवाब सामने रखकर चुनो।',
  },
];

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
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="container flex h-16 items-center justify-between">
          <Brand href="/" />
          <nav className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="#tools">Tools</Link>
            </Button>
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <Link href="#pricing">Pricing</Link>
            </Button>
            <ThemeToggle className="hidden sm:inline-flex" />
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
        <section className="aurora container py-20 text-center sm:py-28">
          <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl">
            One Prompt. Multiple AI Models. Better Results.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
            एक ही प्रॉम्प्ट दो मॉडल को भेजो और दोनों जवाब साथ-साथ देखो — शब्दों में भी, तस्वीरों में भी।
          </p>

          {/* The composer, as a doorway. Someone who lands here should be able to start typing
              rather than hunt for a Sign up button; the prompt travels with them into the app. */}
          <HeroPrompt signedIn={Boolean(user)} />

          <p className="mt-4 text-sm text-muted-foreground">
            फ़्री प्लान शामिल है। कार्ड की ज़रूरत नहीं।
          </p>

          <ComparisonDemo />
        </section>

        {/* Tools */}
        <section id="tools" className="border-t border-border/60 py-20">
          <div className="container">
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="text-3xl font-semibold tracking-tight">हमारे AI टूल्स</h2>
              <p className="mt-3 text-muted-foreground">
                सब कुछ ब्राउज़र में — कुछ इंस्टॉल करने की ज़रूरत नहीं।
              </p>
            </div>
            <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {TOOLS.map((tool) => {
                const Icon = tool.icon;
                return (
                  <Link
                    key={tool.title}
                    href={tool.href}
                    className="group rounded-2xl border border-border/70 bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/40"
                  >
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <Icon className="h-5 w-5" />
                    </span>
                    <p className="mt-3.5 font-medium">{tool.title}</p>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
                      {tool.body}
                    </p>
                    <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-primary opacity-0 transition-opacity group-hover:opacity-100">
                      खोलो <ArrowRight className="h-3.5 w-3.5" />
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
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
/**
 * A composer that does not compose.
 *
 * It cannot answer anything — there is no session yet — so it carries whatever was typed to signup
 * (or straight into the app, for someone already signed in) rather than pretending to stream and
 * then demanding an account halfway through.
 */
function HeroPrompt({ signedIn }: { signedIn: boolean }) {
  const [value, setValue] = useState('');
  const destination = signedIn ? '/chat' : '/signup';
  const href = value.trim() ? `${destination}?prompt=${encodeURIComponent(value.trim())}` : destination;

  return (
    <form
      action={destination}
      onSubmit={(e) => {
        e.preventDefault();
        window.location.href = href;
      }}
      className="mx-auto mt-9 flex max-w-[620px] items-center gap-1.5 rounded-full border border-border/70 bg-card p-1.5 pl-5 shadow-xl shadow-primary/5"
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="कुछ भी पूछो…"
        aria-label="प्रॉम्प्ट"
        className="min-w-0 flex-1 bg-transparent py-2 text-[15px] outline-none placeholder:text-muted-foreground"
      />
      <button
        type="submit"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        {signedIn ? 'खोलो' : 'शुरू करो'}
        <ArrowRight className="h-4 w-4" />
      </button>
    </form>
  );
}

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
                <span className="text-sm font-medium">{model.tier}</span>
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
