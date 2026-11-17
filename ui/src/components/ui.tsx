// 공통 부품 - docs/design/components.md 1~3, 10, 11, 14
import { useEffect, useRef, useState, type ReactNode, type ButtonHTMLAttributes } from "react";
import { AlertTriangle, CheckCircle2, Copy, Globe, Info, XCircle } from "lucide-react";
import { t } from "../lib/i18n";
import { useToast } from "../lib/store";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "link" | "danger" | "danger-fill";
  size?: "sm" | "md" | "lg";
  busy?: boolean;
  icon?: ReactNode;
  internet?: boolean; // 인터넷을 쓰는 단추는 지구본(components.md 1)
};

export function Button({ variant = "secondary", size = "md", busy, icon, internet, children, className, disabled, ...rest }: BtnProps) {
  return (
    <button
      className={`btn btn-${variant} ${size !== "md" ? `btn-${size}` : ""} ${className ?? ""}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="spinner" aria-hidden /> : internet ? <Globe size={14} aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <Tip text={label}>
      <button className="icon-btn" aria-label={label} {...rest}>
        {children}
      </button>
    </Tip>
  );
}

export function Tip({ text, children }: { text?: ReactNode; children: ReactNode }) {
  if (!text) return <>{children}</>;
  return (
    <span className="tip">
      {children}
      <span className="tip-body" role="tooltip">
        {text}
      </span>
    </span>
  );
}

export function Badge({ tone = "outline", icon, tip, children }: { tone?: "outline" | "warn" | "danger" | "gray" | "accent" | "ok"; icon?: ReactNode; tip?: ReactNode; children: ReactNode }) {
  const b = (
    <span className={`badge ${tone !== "outline" ? `badge-${tone}` : ""}`} tabIndex={tip ? 0 : undefined}>
      {icon}
      {children}
    </span>
  );
  return tip ? <Tip text={tip}>{b}</Tip> : b;
}

export type Tone = "ok" | "warn" | "bad" | "gray" | "accent";
export function StatusDot({ tone, spin, children, tip }: { tone: Tone; spin?: boolean; children: ReactNode; tip?: ReactNode }) {
  const el = (
    <span className={`status ${tone}`}>
      {spin ? <span className="spinner" aria-hidden /> : <span className={`dot ${tone}`} aria-hidden />}
      <span className="txt">{children}</span>
    </span>
  );
  return tip ? <Tip text={tip}>{el}</Tip> : el;
}

export function Progress({ value, paused, bad, label }: { value: number; paused?: boolean; bad?: boolean; label?: string }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <div
      className={`progress ${paused ? "paused" : ""} ${bad ? "bad" : ""}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
      aria-label={label}
    >
      <i style={{ width: `${v * 100}%` }} />
    </div>
  );
}

export function Banner({ tone, title, body, children }: { tone: "danger" | "warning" | "info" | "ok"; title: ReactNode; body?: ReactNode; children?: ReactNode }) {
  const Icon = tone === "danger" ? XCircle : tone === "warning" ? AlertTriangle : tone === "ok" ? CheckCircle2 : Info;
  return (
    <div className={`banner ${tone}`} role={tone === "danger" ? "alert" : "status"} aria-live={tone === "danger" ? "assertive" : "polite"}>
      <Icon size={18} style={{ flex: "none", marginTop: 2 }} aria-hidden />
      <div className="grow">
        <div className="b-title">{title}</div>
        {body && <div className="t-body">{body}</div>}
      </div>
      {children && <div className="b-actions">{children}</div>}
    </div>
  );
}

export function Dialog({ title, children, foot, onClose, wide }: { title: ReactNode; children: ReactNode; foot?: ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("button, input, [tabindex]");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      prev?.focus();
    };
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} ref={ref}>
        <div className="dialog-body">
          <h2 className="t-h2" style={{ marginBottom: 12 }}>
            {title}
          </h2>
          {children}
        </div>
        {foot && <div className="dialog-foot">{foot}</div>}
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <div className="t-h2">{title}</div>
      {body && <div>{body}</div>}
      {action}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}

export function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const toast = useToast();
  return (
    <IconButton
      label={label ?? t("common.copy")}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        toast(t("common.copied"));
      }}
    >
      <Copy size={16} />
    </IconButton>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}
