import type { ReactNode } from "react";

type FormSectionProps = {
  title: string;
  description?: string;
  optional?: boolean;
  children: ReactNode;
};

export default function FormSection({ title, description, optional, children }: FormSectionProps) {
  return (
    <section className="kv-form-section">
      <header className="kv-form-section__header">
        <div>
          <h3 className="kv-form-section__title">
            {title}
            {optional ? <span className="kv-form-section__optional">Optional</span> : null}
          </h3>
          {description ? <p className="kv-form-section__desc">{description}</p> : null}
        </div>
      </header>
      <div className="form-grid">{children}</div>
    </section>
  );
}
