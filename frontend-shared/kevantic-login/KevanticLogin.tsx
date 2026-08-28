import React, { FormEvent, useState } from "react";
import "./kevantic-login.css";

type PortalType = "customer" | "admin";

interface KevanticLoginProps {
  portal: PortalType;

  logoSrc: string;
  backgroundSrc: string;

  loading?: boolean;
  error?: string | null;

  onLogin: (email: string, password: string) => Promise<void> | void;
}

export default function KevanticLogin({
  portal,
  logoSrc,
  backgroundSrc,
  loading = false,
  error = null,
  onLogin,
}: KevanticLoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!email.trim() || !password) {
      return;
    }

    await onLogin(email.trim(), password);
  };

  return (
    <main
      className="kevantic-login"
      style={
        {
          "--kevantic-login-bg": `url("${backgroundSrc}")`,
        } as React.CSSProperties
      }
    >
      <div className="kevantic-login__background" />

      <div className="kevantic-login__atmosphere" />

      <section
        className="kevantic-login__card"
        aria-label={
          portal === "admin"
            ? "KEVANTIC administrator login"
            : "KEVANTIC customer login"
        }
      >
        <div className="kevantic-login__card-inner">
          <header className="kevantic-login__header">
            <img
              src={logoSrc}
              alt="KEVANTIC Cyber Security"
              className="kevantic-login__logo"
              draggable={false}
            />

            <h1 className="kevantic-login__title">
              KEVANTIC CYBER SECURITY
              <span>CONTROL PLANE</span>
            </h1>

            <p className="kevantic-login__subtitle">AI-Assisted Managed SOC Platform</p>
          </header>

          <form className="kevantic-login__form" onSubmit={handleSubmit} noValidate>
            <div className="kevantic-login__field">
              <label htmlFor={`${portal}-email`}>Email</label>

              <input
                id={`${portal}-email`}
                name="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={loading}
                required
              />
            </div>

            <div className="kevantic-login__field">
              <label htmlFor={`${portal}-password`}>Password</label>

              <input
                id={`${portal}-password`}
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={loading}
                required
              />
            </div>

            {error && (
              <div className="kevantic-login__error" role="alert">
                {error}
              </div>
            )}

            <button className="kevantic-login__button" type="submit" disabled={loading}>
              <span>{loading ? "Signing In..." : "Sign In"}</span>
            </button>
          </form>

          <footer className="kevantic-login__footer">
            <a className="kevantic-login__support" href="mailto:soc@kevantic.com">
              Support: soc@kevantic.com
            </a>

            <p className="kevantic-login__copyright">
              © 2026 KEVANTIC Cyber Security. All rights reserved.
            </p>
          </footer>
        </div>
      </section>
    </main>
  );
}
