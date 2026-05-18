import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import privacyMd from "@/legal/PRIVACY.md?raw";
import termsMd from "@/legal/TERMS.md?raw";
import { LandingFooter } from "@/components/LandingFooter";

type Document = "privacy" | "terms";

const DOCUMENTS: Record<Document, { title: string; body: string }> = {
  privacy: { title: "Privacy Policy", body: privacyMd },
  terms: { title: "Terms of Service", body: termsMd },
};

export function LegalPage({ doc }: { doc: Document }) {
  const { body } = DOCUMENTS[doc];
  return (
    <div className="wc-landing-bg">
      <header className="wc-landing-nav">
        <Link to="/" className="wc-landing-brand">
          <span className="wc-landing-brand__mark">W</span>
          Whycron
        </Link>
        <nav className="wc-landing-nav__links">
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
        </nav>
        <Link to="/login" className="wc-landing-cta wc-landing-cta--ghost">
          Sign in
        </Link>
      </header>

      <main className="wc-legal">
        <article className="wc-legal__content">
          <ReactMarkdown>{body}</ReactMarkdown>
        </article>
      </main>

      <LandingFooter />
    </div>
  );
}
