import { Link } from "react-router-dom";

export function LandingFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="wc-landing-footer">
      <div className="wc-landing-footer__row">
        <div>
          <p className="wc-landing-footer__brand">Whycron</p>
          <p className="wc-landing-footer__copy">
            Cron monitoring that tells you why.
          </p>
        </div>
        <nav className="wc-landing-footer__nav">
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a
            href="mailto:sakshamdhingra1305@gmail.com"
            aria-label="Contact email"
          >
            Contact
          </a>
          <a
            href="https://github.com/Saksham1367/Whycron"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </nav>
      </div>
      <p className="wc-landing-footer__legal">
        © {year} Saksham Dhingra · Faridabad, India
      </p>
    </footer>
  );
}
