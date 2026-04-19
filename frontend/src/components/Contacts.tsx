import { Mail, Phone, User2 } from "lucide-react";
import type { Contact } from "../types";
import { cn } from "../lib/utils";

function sanitizePhone(phone: string): string {
  return phone.replace(/[^+0-9]/g, "");
}

export function ContactCell({ contacts }: { contacts?: Contact[] }) {
  if (!contacts || contacts.length === 0) {
    return (
      <span className="text-xs italic text-muted-foreground">No contact listed</span>
    );
  }
  const primary = contacts[0];
  const extraCount = contacts.length - 1;
  return (
    <div className="space-y-1">
      {primary.name && (
        <div className="flex items-start gap-1.5 text-[13px] font-medium text-foreground">
          <User2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
          <span className="leading-tight">{primary.name}</span>
        </div>
      )}
      {primary.phone && (
        <a
          href={`tel:${sanitizePhone(primary.phone)}`}
          onClick={(e) => e.stopPropagation()}
          className="flex items-start gap-1.5 text-[12.5px] text-muted-foreground hover:text-brand-700"
        >
          <Phone className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />
          <span className="leading-tight">{primary.phone}</span>
        </a>
      )}
      {primary.email && (
        <a
          href={`mailto:${primary.email}`}
          onClick={(e) => e.stopPropagation()}
          className="flex items-start gap-1.5 text-[12.5px] text-muted-foreground hover:text-brand-700"
        >
          <Mail className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />
          <span className="truncate leading-tight" title={primary.email}>
            {primary.email}
          </span>
        </a>
      )}
      {extraCount > 0 && (
        <span className="inline-block rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
          +{extraCount} more
        </span>
      )}
    </div>
  );
}

export function ContactList({
  contacts,
  className,
}: {
  contacts?: Contact[];
  className?: string;
}) {
  if (!contacts || contacts.length === 0) {
    return (
      <p className={cn("text-[13.5px] text-muted-foreground", className)}>
        No contact information listed.
      </p>
    );
  }
  return (
    <ul className={cn("space-y-2.5", className)}>
      {contacts.map((c, i) => (
        <li
          key={`${c.name}-${c.phone}-${c.email}-${i}`}
          className="rounded-lg border border-border bg-white p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <User2 className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-[13.5px] font-semibold text-foreground">
              {c.name || "Unnamed contact"}
            </span>
            {c.role && (
              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.05em] text-slate-600">
                {c.role}
              </span>
            )}
          </div>
          <div className="mt-1.5 flex flex-col gap-1 text-[13px] text-muted-foreground sm:flex-row sm:flex-wrap sm:gap-x-4">
            {c.phone && (
              <a
                href={`tel:${sanitizePhone(c.phone)}`}
                className="inline-flex items-center gap-1.5 hover:text-brand-700"
              >
                <Phone className="h-3 w-3 text-slate-400" />
                {c.phone}
              </a>
            )}
            {c.email && (
              <a
                href={`mailto:${c.email}`}
                className="inline-flex items-center gap-1.5 hover:text-brand-700"
              >
                <Mail className="h-3 w-3 text-slate-400" />
                {c.email}
              </a>
            )}
            {!c.phone && !c.email && (
              <span className="italic">No phone or email provided.</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
