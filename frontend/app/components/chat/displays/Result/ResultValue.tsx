"use client";

import React from "react";
import { ColumnMeta } from "@/app/types/results";
import { formatValue, safeUrl } from "@/app/utils/formatValue";

/** One result value as text, or as a link for a URL column. */
const ResultValue: React.FC<{ value: unknown; column?: ColumnMeta; className?: string }> = ({
  value,
  column,
  className = "",
}) => {
  const href = column?.role === "url" || column?.role === "image" ? safeUrl(value) : null;
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className={`text-highlight underline-offset-2 hover:underline break-all ${className}`}
      >
        {href}
      </a>
    );
  }
  return <span className={className}>{formatValue(value, column?.type)}</span>;
};

export default ResultValue;
