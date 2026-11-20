import clsx from "clsx";
import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { Icon, type IconName } from "./icons";

/* ───────────── Button ───────────── */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "link";
const BTN: Record<Variant, string> = {
  primary: "bg-forest-800 text-white hover:bg-forest-900 shadow-card disabled:bg-forest-800/50",
  secondary: "bg-white text-ink border border-line-strong hover:bg-paper-2 shadow-card",
  ghost: "text-ink-2 hover:bg-paper-2",
  danger: "bg-white text-bad-700 border border-bad-100 hover:bg-bad-50",
  link: "text-forest-700 hover:text-forest-900 underline-offset-4 hover:underline px-0",
};
const SIZE = { sm: "h-8 px-3 text-sm gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-5 text-base gap-2" };
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof SIZE; icon?: IconName; loading?: boolean; full?: boolean };
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "primary", size = "md", icon, loading, full, className, children, disabled, type = "button", ...rest }, ref) {
  return (
    <button ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={clsx("inline-flex items-center justify-center rounded-xl font-medium transition-colors focus-ring disabled:cursor-not-allowed whitespace-nowrap",
        BTN[variant], variant !== "link" && SIZE[size], full && "w-full", className)} {...rest}>
      {loading ? <Spinner size={16} /> : icon && <Icon name={icon} size={size === "sm" ? 16 : 18} />}
      {children}
    </button>
  );
});

export function ButtonLink({ to, variant = "primary", size = "md", icon, className, children, external }:
  { to: string; variant?: Variant; size?: keyof typeof SIZE; icon?: IconName; className?: string; children: ReactNode; external?: boolean }) {
  const cls = clsx("inline-flex items-center justify-center rounded-xl font-medium transition-colors focus-ring whitespace-nowrap", BTN[variant], variant !== "link" && SIZE[size], className);
  const inner = <>{icon && <Icon name={icon} size={18} />}{children}</>;
  return external
    ? <a href={to} className={cls} target="_blank" rel="noopener noreferrer">{inner}</a>
    : <Link to={to} className={cls}>{inner}</Link>;
}

/* ───────────── Surfaces ───────────── */
export function Card({ className, children, as: As = "div", ...rest }: { className?: string; children: ReactNode; as?: any } & Record<string, unknown>) {
  return <As className={clsx("rounded-2xl border border-line bg-white shadow-card dark:bg-forest-950 dark:border-white/10", className)} {...rest}>{children}</As>;
}
export function CardHeader({ title, sub, action, id }: { title: ReactNode; sub?: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 pt-5">
      <div className="min-w-0">
        <h2 id={id} className="text-[15px] font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-sm text-ink-3">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

/* ───────────── Badge ───────────── */
type Tone = "ok" | "warn" | "bad" | "info" | "neutral" | "brand";
const TONE: Record<Tone, string> = {
  ok: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  warn: "bg-warn-50 text-warn-700 ring-warn-600/20",
  bad: "bg-bad-50 text-bad-700 ring-bad-600/20",
  info: "bg-info-50 text-info-600 ring-info-600/20",
  neutral: "bg-paper-2 text-ink-2 ring-ink/10",
  brand: "bg-forest-50 text-forest-800 ring-forest-800/15",
};
export function Badge({ tone = "neutral", children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: IconName }) {
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONE[tone], className)}>
    {icon && <Icon name={icon} size={13} />}{children}</span>;
}

/* ───────────── Form fields ───────────── */
type FieldProps = { label: string; hint?: ReactNode; error?: string; className?: string };
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & FieldProps>(function Input(
  { label, hint, error, className, id, ...rest }, ref) {
  const auto = useId(); const fid = id ?? auto;
  return (
    <div className={className}>
      <label htmlFor={fid} className="mb-1.5 block text-sm font-medium text-ink-2">{label}</label>
      <input ref={ref} id={fid} aria-invalid={!!error || undefined} aria-describedby={error ? `${fid}-err` : hint ? `${fid}-hint` : undefined}
        className={clsx("h-11 w-full rounded-xl border bg-white px-3.5 text-[15px] text-ink placeholder:text-ink-4 focus-ring transition-colors",
          error ? "border-bad-600" : "border-line-strong hover:border-ink-4")} {...rest} />
      {error ? <p id={`${fid}-err`} className="mt-1.5 text-sm text-bad-700">{error}</p>
        : hint ? <p id={`${fid}-hint`} className="mt-1.5 text-xs text-ink-3">{hint}</p> : null}
    </div>
  );
});
export function Textarea({ label, hint, error, className, id, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps) {
  const auto = useId(); const fid = id ?? auto;
  return (
    <div className={className}>
      <label htmlFor={fid} className="mb-1.5 block text-sm font-medium text-ink-2">{label}</label>
      <textarea id={fid} aria-invalid={!!error || undefined} className={clsx("w-full rounded-xl border bg-white px-3.5 py-2.5 text-[15px] focus-ring", error ? "border-bad-600" : "border-line-strong")} {...rest} />
      {error ? <p className="mt-1.5 text-sm text-bad-700">{error}</p> : hint ? <p className="mt-1.5 text-xs text-ink-3">{hint}</p> : null}
    </div>
  );
}
export function Select({ label, hint, className, id, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & FieldProps) {
  const auto = useId(); const fid = id ?? auto;
  return (
    <div className={className}>
      <label htmlFor={fid} className="mb-1.5 block text-sm font-medium text-ink-2">{label}</label>
      <select id={fid} className="h-11 w-full rounded-xl border border-line-strong bg-white px-3 text-[15px] focus-ring" {...rest}>{children}</select>
      {hint && <p className="mt-1.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

/* ───────────── Feedback states ───────────── */
export function Spinner({ size = 20, className }: { size?: number; className?: string }) {
  return <svg className={clsx("animate-spin", className)} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".2" strokeWidth="3" fill="none" />
    <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" /></svg>;
}
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-paper-3", className)} aria-hidden="true" />;
}
export function Loading({ label = "Loading…", className }: { label?: string; className?: string }) {
  return <div role="status" className={clsx("flex items-center justify-center gap-3 py-16 text-ink-3", className)}><Spinner /> <span>{label}</span></div>;
}
export function EmptyState({ icon = "leaf", title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-forest-50 text-forest-700"><Icon name={icon} size={24} /></div>
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {children && <div className="mt-1.5 max-w-sm text-sm text-ink-3">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
export function ErrorState({ error, onRetry, title = "Something went wrong" }: { error: unknown; onRetry?: () => void; title?: string }) {
  const msg = error instanceof Error ? error.message : "Please try again.";
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-3 grid h-11 w-11 place-items-center rounded-2xl bg-bad-50 text-bad-700"><Icon name="alert" /></div>
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-ink-3">{msg}</p>
      {onRetry && <Button variant="secondary" className="mt-4" onClick={onRetry} icon="rotate">Try again</Button>}
    </div>
  );
}
export function Notice({ tone = "info", title, children, icon }: { tone?: Exclude<Tone, "neutral" | "brand">; title?: ReactNode; children?: ReactNode; icon?: IconName }) {
  const t = { ok: "bg-emerald-50 border-emerald-600/20 text-emerald-700", warn: "bg-warn-50 border-warn-600/25 text-warn-700",
    bad: "bg-bad-50 border-bad-600/20 text-bad-700", info: "bg-info-50 border-info-600/20 text-info-600" }[tone];
  const ic: IconName = icon ?? (tone === "ok" ? "check" : tone === "info" ? "info" : "alert");
  return (
    <div className={clsx("flex gap-3 rounded-xl border px-4 py-3 text-sm", t)} role={tone === "bad" ? "alert" : "note"}>
      <Icon name={ic} size={18} className="mt-0.5 shrink-0" />
      <div className="min-w-0 text-ink-2">{title && <p className={clsx("font-semibold", t.split(" ").pop())}>{title}</p>}{children}</div>
    </div>
  );
}

/* ───────────── Confidence meter ───────────── */
export function ConfidenceMeter({ value, label = "Confidence", calibrated }: { value: number; label?: string; calibrated?: boolean }) {
  const tone = value >= 0.7 ? "bg-emerald-600" : value >= 0.4 ? "bg-warn-600" : "bg-bad-600";
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-sm">
        <span className="text-ink-3">{label}{calibrated && <span className="ml-1 text-2xs text-ink-4">(calibrated)</span>}</span>
        <strong className="tabular-nums text-ink">{(value * 100).toFixed(1)}%</strong>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-paper-3" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}>
        <div className={clsx("h-full rounded-full transition-[width] duration-700", tone)} style={{ width: `${Math.max(2, value * 100)}%` }} />
        <i className="absolute inset-y-0 left-[40%] w-px bg-white" /><i className="absolute inset-y-0 left-[70%] w-px bg-white" />
      </div>
      <div className="mt-1 flex justify-between text-2xs text-ink-4"><span>Inconclusive</span><span className="ml-[22%]">Verify</span><span>Confident</span></div>
    </div>
  );
}

export function PageHeader({ title, sub, action, eyebrow }: { title: ReactNode; sub?: ReactNode; action?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-forest-600">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-[15px] text-ink-3">{sub}</p>}
      </div>
      {action && <div className="flex shrink-0 gap-2">{action}</div>}
    </div>
  );
}
