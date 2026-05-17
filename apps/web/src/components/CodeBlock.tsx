import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  error?: boolean;
}

export function CodeBlock({ children, error }: Props) {
  return (
    <pre className={`wc-code-block ${error ? "wc-code-block--err" : ""}`}>
      {children}
    </pre>
  );
}
