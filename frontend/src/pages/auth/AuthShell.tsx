import type { ReactNode } from "react";
import { Card } from "../../components/ui/ui";
export default function AuthShell({ title, sub, children, footer }: { title: string; sub?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-md flex-col px-5 py-12 sm:py-20">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {sub && <p className="mt-1.5 text-ink-3">{sub}</p>}
      <Card className="mt-6 p-6">{children}</Card>
      {footer && <div className="mt-5 text-center text-sm text-ink-3">{footer}</div>}
    </div>
  );
}
