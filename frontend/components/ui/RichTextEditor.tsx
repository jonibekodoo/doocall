"use client";

/** Dependency-free Word-like editor (contentEditable + execCommand).
 * Emits HTML; the server sanitises it with an allow-list before storing. */

import {
  Bold,
  Heading2,
  Heading3,
  Italic,
  Link2,
  List,
  ListOrdered,
  Pilcrow,
  RemoveFormatting,
  Underline,
} from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

const TOOLS: Array<{
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  cmd: string;
  arg?: string;
}> = [
  { icon: Bold, title: "Qalin", cmd: "bold" },
  { icon: Italic, title: "Kursiv", cmd: "italic" },
  { icon: Underline, title: "Tagiga chizilgan", cmd: "underline" },
  { icon: Heading2, title: "Sarlavha", cmd: "formatBlock", arg: "H2" },
  { icon: Heading3, title: "Kichik sarlavha", cmd: "formatBlock", arg: "H3" },
  { icon: Pilcrow, title: "Oddiy matn", cmd: "formatBlock", arg: "P" },
  { icon: List, title: "Ro'yxat", cmd: "insertUnorderedList" },
  { icon: ListOrdered, title: "Raqamli ro'yxat", cmd: "insertOrderedList" },
  { icon: RemoveFormatting, title: "Formatni tozalash", cmd: "removeFormat" },
];

export function RichTextEditor({
  value,
  onChange,
  minHeight = 360,
  className,
}: {
  value: string;
  onChange: (html: string) => void;
  minHeight?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  // Push external value in only when it differs (never on our own keystrokes,
  // so the caret is not reset).
  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== value) el.innerHTML = value;
  }, [value]);

  const emit = () => onChange(ref.current?.innerHTML ?? "");
  const exec = (cmd: string, arg?: string) => {
    ref.current?.focus();
    document.execCommand(cmd, false, arg);
    emit();
  };
  const link = () => {
    const url = window.prompt("Havola (https://...)");
    if (url) exec("createLink", url);
  };

  return (
    <div className={cn("rounded-lg border border-border bg-surface", className)}>
      <div className="flex flex-wrap items-center gap-1 border-b border-border p-1.5">
        {TOOLS.map(({ icon: Icon, title, cmd, arg }) => (
          <button
            key={title}
            type="button"
            title={title}
            onMouseDown={(e) => e.preventDefault()} // keep selection
            onClick={() => exec(cmd, arg)}
            className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-fg"
          >
            <Icon className="size-4" />
          </button>
        ))}
        <button
          type="button"
          title="Havola"
          onMouseDown={(e) => e.preventDefault()}
          onClick={link}
          className="grid size-8 place-items-center rounded-md text-fg-muted hover:bg-surface-2 hover:text-fg"
        >
          <Link2 className="size-4" />
        </button>
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={emit}
        onBlur={emit}
        style={{ minHeight }}
        className="prose-offer p-4 text-sm leading-relaxed focus:outline-none [&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mb-1.5 [&_h3]:mt-2 [&_h3]:text-base [&_h3]:font-semibold [&_p]:mb-2 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:text-accent [&_a]:underline"
      />
    </div>
  );
}
