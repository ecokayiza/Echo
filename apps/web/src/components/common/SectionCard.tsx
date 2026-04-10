import type { ReactNode } from "react";

interface SectionCardProps {
  eyebrow?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

export function SectionCard({
  actions,
  bodyClassName = "",
  children,
  className = "",
  description,
  eyebrow,
  title,
}: SectionCardProps) {
  return (
    <section className={`section-card${className ? ` ${className}` : ""}`}>
      <header className="section-card__header">
        <div className="section-card__title-block">
          {eyebrow ? <p className="section-card__eyebrow">{eyebrow}</p> : null}
          <h2 className="section-card__title">{title}</h2>
          {description ? <p className="section-card__description">{description}</p> : null}
        </div>
        {actions ? <div className="section-card__actions">{actions}</div> : null}
      </header>
      <div className={`section-card__body${bodyClassName ? ` ${bodyClassName}` : ""}`}>{children}</div>
    </section>
  );
}
