"use client";

import React, { useState } from "react";
import { GoCheck, GoPencil, GoX } from "react-icons/go";
import { FaSpinner } from "react-icons/fa";

const SOURCE_LABELS: Record<string, string> = {
  generated: "AI",
  user: "edited",
  comment: "DB comment",
};

type Props = {
  value: string | null;
  source: string | null;
  placeholder?: string;
  // Resolves on success; empty text resets the description.
  onSave: (text: string) => Promise<void>;
};

/** Inline-editable description shown to (and used by) the SQL agent. */
export default function EditableDescription({
  value,
  source,
  placeholder = "Add a description",
  onSave,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setDraft(value || "");
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave(draft.trim());
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    }
    setSaving(false);
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-1 w-full">
        <textarea
          autoFocus
          value={draft}
          maxLength={2000}
          rows={2}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              save();
            }
            if (e.key === "Escape") setEditing(false);
          }}
          className="w-full text-xs bg-background border border-foreground rounded-md px-2 py-1 text-primary focus:outline-none focus:border-accent resize-y"
        />
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-1 text-accent hover:opacity-80 disabled:opacity-50"
          >
            {saving ? <FaSpinner className="animate-spin" size={10} /> : <GoCheck size={12} />}
            Save
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={saving}
            className="flex items-center gap-1 text-muted-foreground hover:text-primary"
          >
            <GoX size={12} />
            Cancel
          </button>
          <span className="text-muted-foreground">Empty = reset to generated</span>
        </div>
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-2 w-full">
      <span className={`text-xs ${value ? "text-primary" : "text-muted-foreground italic"}`}>
        {value || placeholder}
      </span>
      {value && source && SOURCE_LABELS[source] && (
        <span className="text-[10px] uppercase tracking-wide bg-foreground/40 text-muted-foreground px-1 rounded flex-shrink-0">
          {SOURCE_LABELS[source]}
        </span>
      )}
      <button
        onClick={start}
        title="Edit description"
        className="text-muted-foreground hover:text-accent opacity-60 group-hover:opacity-100 flex-shrink-0"
      >
        <GoPencil size={12} />
      </button>
    </div>
  );
}
