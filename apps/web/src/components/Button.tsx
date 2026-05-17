import type { ButtonHTMLAttributes, ReactNode } from "react";
import { SymbolIcon } from "./SymbolIcon";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: string;
  children?: ReactNode;
}

export function Button({
  variant = "primary",
  icon,
  children,
  type,
  ...rest
}: Props) {
  return (
    <button
      type={type ?? "button"}
      className={`wc-btn wc-btn--${variant}`}
      {...rest}
    >
      {icon ? <SymbolIcon name={icon} size="1.05rem" /> : null}
      {children}
    </button>
  );
}
