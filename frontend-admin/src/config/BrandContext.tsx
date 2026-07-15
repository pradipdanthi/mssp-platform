import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { loadAppConfig } from "./loadAppConfig";
import type { AppConfig } from "./types";

interface BrandContextValue {
  config: AppConfig;
}

const BrandContext = createContext<BrandContextValue | undefined>(undefined);

export function BrandProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadAppConfig()
      .then((loaded) => {
        if (cancelled) return;
        document.title = loaded.documentTitle;
        setConfig(loaded);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Unable to load application branding configuration.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="app-loading app-config-error" role="alert">
        <strong>Configuration error</strong>
        <span>{error}</span>
        <span>Reload the page after checking public/app-config.json.</span>
      </div>
    );
  }

  if (!config) {
    return <div className="app-loading">Loading portal...</div>;
  }

  return <BrandContext.Provider value={{ config }}>{children}</BrandContext.Provider>;
}

export function useBrand(): AppConfig {
  const ctx = useContext(BrandContext);
  if (!ctx) {
    throw new Error("useBrand must be used within a BrandProvider");
  }
  return ctx.config;
}
