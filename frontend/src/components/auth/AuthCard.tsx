import { Link } from "react-router-dom";

interface AuthCardProps {
  title: string;
  subtitle: string;
  footerText: string;
  footerLinkLabel: string;
  footerLinkTo: string;
  children: React.ReactNode;
}

export function AuthCard({
  title,
  subtitle,
  footerText,
  footerLinkLabel,
  footerLinkTo,
  children,
}: AuthCardProps) {
  return (
    <div className="auth-stage">
      <section className="auth-panel" aria-label={title}>
        <div className="auth-panel__head">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {children}
        <p className="auth-panel__foot">
          {footerText} <Link to={footerLinkTo}>{footerLinkLabel}</Link>
        </p>
      </section>
    </div>
  );
}
