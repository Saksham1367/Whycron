import { Link, Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { SymbolIcon } from "@/components/SymbolIcon";
import { LandingFooter } from "@/components/LandingFooter";

export function LandingScreen() {
  const { session, loading } = useAuth();

  // Signed-in visitors skip the marketing page and go straight to the
  // dashboard. The auth-provider loading state is short — render a
  // single empty paint instead of flashing the marketing copy.
  if (loading) return <div className="wc-landing-bg" />;
  if (session) return <Navigate to="/monitors" replace />;

  return (
    <div className="wc-landing-bg">
      <header className="wc-landing-nav">
        <span className="wc-landing-brand">
          <span className="wc-landing-brand__mark">W</span>
          Whycron
        </span>
        <nav className="wc-landing-nav__links">
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#pricing">Pricing</a>
          <a href="#upcoming">Roadmap</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="wc-landing-nav__auth">
          <Link to="/login" className="wc-landing-cta wc-landing-cta--ghost">
            Sign in
          </Link>
          <Link
            to="/login?mode=signup"
            className="wc-landing-cta wc-landing-cta--primary"
          >
            Sign up
          </Link>
        </div>
      </header>

      <main className="wc-landing-main">
        <section className="wc-hero">
          <p className="wc-hero__eyebrow">
            Cron monitoring · AI explanations · Auto-fix PRs
          </p>
          <h1 className="wc-hero__title">
            Cron monitoring that tells you <em>why</em>.
          </h1>
          <p className="wc-hero__sub">
            Stop staring at red dots. Whycron sends you a plain-English root
            cause from Claude on every failure — and can open a GitHub PR
            with the fix, ready to merge. Both in the minute the alert lands.
          </p>
          <div className="wc-hero__highlights">
            <span className="wc-hero__pill">
              <SymbolIcon name="psychology" size=".95rem" filled />
              AI explanation on every failure
            </span>
            <span className="wc-hero__pill">
              <SymbolIcon name="merge" size=".95rem" filled />
              Optional fix-PR opened in your repo
            </span>
          </div>
          <div className="wc-hero__cta-row">
            <Link to="/login?mode=signup" className="wc-landing-cta wc-landing-cta--primary">
              Start free <SymbolIcon name="arrow_forward" size="1.05rem" />
            </Link>
            <a href="#how-it-works" className="wc-landing-cta wc-landing-cta--ghost">
              See how it works
            </a>
          </div>
          <p className="wc-hero__fineprint">
            No credit card required · 5 monitors free forever
          </p>

          <div className="wc-hero__demo">
            <DemoAlertCard />
          </div>
        </section>

        <section id="features" className="wc-section">
          <p className="wc-section__eyebrow">What you get today</p>
          <h2 className="wc-section__title">
            The monitoring tool that does the post-mortem for you.
          </h2>
          <div className="wc-feature-grid">
            <Feature
              icon="psychology"
              title="AI failure explanations"
              body="When a job fails, Claude reads the redacted logs, identifies the root cause in plain English, and suggests a fix. No more 4am Slack rituals."
              accent
            />
            <Feature
              icon="merge"
              title="Auto-fix pull requests"
              body="Whycron can take Claude's suggested fix and open a pull request against your repo, ready for review. Approve and merge from the same alert."
              accent
            />
            <Feature
              icon="schedule_send"
              title="Cron expression preview"
              body="Type a cron string and see the next five fire times instantly — before you save the monitor. Catches the everyone-knows-they-broke-it 'oops, that's every minute' moments."
            />
            <Feature
              icon="notifications_active"
              title="Alerts where you live"
              body="Email, Slack (threaded follow-ups in one channel), Discord, or a signed webhook to your own service."
            />
            <Feature
              icon="schedule"
              title="Schedule-aware monitoring"
              body="Cron, interval, or on-demand. Late, missed, and timed-out states are detected automatically — no false alarms on slow jobs."
            />
            <Feature
              icon="public"
              title="Public status pages"
              body="Opt-in per monitor. Share live job health with your customers at a clean status.your-domain URL."
            />
            <Feature
              icon="code"
              title="API + SDKs"
              body="REST API with scoped keys. Official Python & Node packages: pip install whycron-sdk, npm install whycron."
            />
            <Feature
              icon="lock"
              title="Built for teams that care"
              body="Multi-tenant from day one. Redaction strips secrets from logs before they ever hit our database or the LLM."
            />
          </div>
        </section>

        <section id="how-it-works" className="wc-section">
          <p className="wc-section__eyebrow">How it works</p>
          <h2 className="wc-section__title">Three steps. Less than five minutes.</h2>
          <ol className="wc-steps">
            <Step
              num={1}
              title="Register the job"
              body="Add a monitor with your cron expression or interval. We give you a unique ping URL."
              snippet="POST /api/v1/monitors"
            />
            <Step
              num={2}
              title="Ping us from your job"
              body="Replace your job command with one that pings before, ends with success, or reports a failure."
              snippet={`# instead of:\n*/5 * * * *  /usr/bin/backup.sh\n\n# do:\n*/5 * * * *  /usr/bin/backup.sh && curl -fs https://whycron.com/p/$TOKEN`}
            />
            <Step
              num={3}
              title="Get the why, not just the what"
              body="When something breaks, the alert in your inbox or Slack already includes the AI-extracted root cause and a suggested fix."
            />
          </ol>
        </section>

        <section id="pricing" className="wc-section">
          <p className="wc-section__eyebrow">Pricing</p>
          <h2 className="wc-section__title">Free to start. Honest to scale.</h2>
          <div className="wc-pricing-grid">
            <PriceCard
              tier="Free"
              price="$0"
              priceSub="forever"
              tagline="Pick this if you're just trying it out."
              perks={[
                "5 monitors",
                "30-day run history",
                "Email + webhook + Discord alerts",
                "Public status page",
                "API + SDKs",
              ]}
              cta="Start free"
            />
            <PriceCard
              tier="Pro"
              price="$9"
              priceSub="per month"
              tagline="For teams who actually run things in production."
              perks={[
                "25 monitors",
                "1-year run history",
                "Everything in Free",
                "AI explanations on every failed run",
                "Slack OAuth + threaded alerts",
                "Priority email support",
              ]}
              cta="Upgrade after signup"
              featured
            />
          </div>
          <p className="wc-pricing__note">
            Need more monitors or SOC2 paperwork? Email{" "}
            <a href="mailto:sakshamdhingra1305@gmail.com">
              sakshamdhingra1305@gmail.com
            </a>{" "}
            — we'll work something out.
          </p>
        </section>

        <section id="upcoming" className="wc-section">
          <p className="wc-section__eyebrow">On the roadmap</p>
          <h2 className="wc-section__title">What's next after launch.</h2>
          <p className="wc-section__lede">
            We ship the boring stuff first. Here's what's actively in
            development or queued for the post-launch sprints — none of
            this is locked, and customer asks promote items up the list.
          </p>
          <div className="wc-upcoming-grid">
            <Upcoming
              icon="dns"
              title="Self-host on your own infrastructure"
              body="Run the whole Whycron stack on your servers via a Docker bundle. Already built on a private branch; release pending demand."
              status="In private beta"
            />
            <Upcoming
              icon="group"
              title="Team management"
              body="Invite teammates with role-based access (owner / member / viewer) and per-monitor permissions. Schema already supports it."
              status="Engineering"
            />
            <Upcoming
              icon="dns_outline"
              title="Custom status-page domains"
              body="Point status.your-company.com at our infrastructure with a CNAME. Keep your branding, lose the whycron.com path."
              status="Planned"
            />
            <Upcoming
              icon="forum"
              title="Slack slash commands"
              body="/whycron status and /whycron pause backups directly from any Slack channel — no dashboard tab switch."
              status="Planned"
            />
            <Upcoming
              icon="terminal"
              title="Go and Bash SDKs"
              body="go get for Go services, a one-liner Bash function for shell scripts and CI pipelines. Python and Node ship at launch; these follow."
              status="Queued"
            />
            <Upcoming
              icon="history"
              title="Webhook delivery log + retries"
              body="A visual log of every alert delivery with one-click retry on the failed ones. Saves you the inevitable 'did it actually send?' debugging."
              status="Planned"
            />
          </div>
        </section>

        <section id="faq" className="wc-section">
          <p className="wc-section__eyebrow">Questions</p>
          <h2 className="wc-section__title">Things people ask before signing up.</h2>
          <div className="wc-faq">
            <FAQ
              q="What exactly is an AI explanation?"
              a="When a monitored job fails or misses its schedule, we ship the redacted logs + the run metadata to Claude (Anthropic's model). Claude returns a one-paragraph root cause plus a concrete suggested fix. That text is included in the alert and stored on the run page so you can revisit it later."
            />
            <FAQ
              q="Are my logs sent to a third-party LLM?"
              a={
                <>
                  Only the redacted ones, and only on failure. Our redactor strips known secret patterns (cloud keys, JWTs, connection strings, etc.) <em>before</em> the log is written to our database and <em>before</em> any LLM call. Anthropic's API does not train on data submitted through it. See our{" "}
                  <Link to="/privacy">Privacy Policy</Link> for the full breakdown.
                </>
              }
            />
            <FAQ
              q="Can I self-host Whycron?"
              a={
                <>
                  A self-hostable Docker bundle is in development — request early access from{" "}
                  <a href="mailto:sakshamdhingra1305@gmail.com?subject=Whycron%20self-host%20access">
                    sakshamdhingra1305@gmail.com
                  </a>
                  . The AI explanations are only available on the hosted product.
                </>
              }
            />
            <FAQ
              q="Which languages have SDKs?"
              a={
                <>
                  Python (<code>pip install whycron-sdk</code>) and Node (
                  <code>npm install whycron</code>) ship today. Both are thin
                  wrappers over the REST API — every language with an HTTP
                  client works too.
                </>
              }
            />
            <FAQ
              q="How do I cancel?"
              a={
                <>
                  Email the administrator directly at{" "}
                  <a href="mailto:sakshamdhingra1305@gmail.com?subject=Whycron%20cancellation">
                    sakshamdhingra1305@gmail.com
                  </a>
                  . No "contact sales", no retention department, no exit
                  interview — Saksham handles it himself. Cancellation
                  takes effect at the end of the period you've already paid
                  for.
                </>
              }
            />
          </div>
        </section>

        <section className="wc-section wc-cta-band">
          <h2 className="wc-cta-band__title">Stop staring at red dots.</h2>
          <p className="wc-cta-band__sub">
            5 monitors free. 5 minutes to set up. Cancel any time, no email required.
          </p>
          <Link to="/login" className="wc-landing-cta wc-landing-cta--primary wc-landing-cta--large">
            Start monitoring free <SymbolIcon name="arrow_forward" size="1.1rem" />
          </Link>
        </section>
      </main>

      <LandingFooter />
    </div>
  );
}

// ── Building blocks ──────────────────────────────────────────────────────────

function Feature({
  icon,
  title,
  body,
  accent,
}: {
  icon: string;
  title: string;
  body: string;
  accent?: boolean;
}) {
  return (
    <article className={`wc-feature ${accent ? "wc-feature--accent" : ""}`}>
      <SymbolIcon
        name={icon}
        size="1.4rem"
        color={accent ? "var(--wc-primary-strong)" : "var(--wc-text-soft)"}
        filled={accent}
      />
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
  );
}

function Upcoming({
  icon,
  title,
  body,
  status,
}: {
  icon: string;
  title: string;
  body: string;
  status: string;
}) {
  return (
    <article className="wc-upcoming">
      <div className="wc-upcoming__head">
        <SymbolIcon name={icon} size="1.2rem" color="var(--wc-text-soft)" />
        <span className="wc-upcoming__status">{status}</span>
      </div>
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
  );
}

function Step({
  num,
  title,
  body,
  snippet,
}: {
  num: number;
  title: string;
  body: string;
  snippet?: string;
}) {
  return (
    <li className="wc-step">
      <span className="wc-step__num">{num}</span>
      <div>
        <h3>{title}</h3>
        <p>{body}</p>
        {snippet && <pre className="wc-step__snippet">{snippet}</pre>}
      </div>
    </li>
  );
}

function PriceCard({
  tier,
  price,
  priceSub,
  tagline,
  perks,
  cta,
  featured,
}: {
  tier: string;
  price: string;
  priceSub: string;
  tagline: string;
  perks: string[];
  cta: string;
  featured?: boolean;
}) {
  return (
    <div className={`wc-price ${featured ? "wc-price--featured" : ""}`}>
      <p className="wc-price__tier">{tier}</p>
      <p className="wc-price__amount">
        {price}{" "}
        <span className="wc-price__sub">{priceSub}</span>
      </p>
      <p className="wc-price__tagline">{tagline}</p>
      <ul>
        {perks.map((p) => (
          <li key={p}>
            <SymbolIcon name="check" size=".95rem" color="var(--wc-primary-strong)" />
            <span>{p}</span>
          </li>
        ))}
      </ul>
      <Link
        to="/login"
        className={`wc-landing-cta ${featured ? "wc-landing-cta--primary" : "wc-landing-cta--ghost"}`}
      >
        {cta}
      </Link>
    </div>
  );
}

function FAQ({ q, a }: { q: string; a: React.ReactNode }) {
  return (
    <details className="wc-faq__item">
      <summary>{q}</summary>
      <div className="wc-faq__answer">{a}</div>
    </details>
  );
}

function DemoAlertCard() {
  return (
    <div className="wc-demo-card">
      <div className="wc-demo-card__head">
        <SymbolIcon name="error" color="var(--wc-danger)" />
        <strong>Nightly backup failed</strong>
        <span className="wc-demo-card__time">just now</span>
      </div>
      <div className="wc-demo-card__meta">
        <span>
          <em>Monitor:</em> nightly-backup
        </span>
        <span>
          <em>Schedule:</em> 0 2 * * *
        </span>
        <span>
          <em>Exit code:</em> 1
        </span>
      </div>
      <div className="wc-demo-card__ai">
        <p className="wc-demo-card__ai-label">AI explanation</p>
        <p>
          <strong>Root cause.</strong> The backup volume hit 100% capacity
          before pg_dump could finish writing the archive.
        </p>
        <p>
          <strong>Suggested fix.</strong> Rotate yesterday's backups out of
          the volume, or expand the volume to {">"}50&nbsp;GB. Confidence:
          high.
        </p>
      </div>
    </div>
  );
}
