"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const REMARK_PLUGINS = [remarkGfm];

const BASE_CLASSES = [
  "flex-grow justify-start items-start text-wrap prose max-w-none prose:w-full break-words",
  "prose-p:leading-relaxed prose-p:my-2",
  "prose-img:hidden",
  "prose-strong:text-primary prose-strong:font-bold",
  "prose-a:text-primary",
  "prose-headings:text-primary prose-headings:text-xl prose-headings:font-heading prose-headings:font-bold",
  "prose-ol:text-primary prose-ol:text-base prose-ol:font-light",
  "prose-ul:text-primary prose-ul:text-base prose-ul:font-normal",
  "prose-code:font-mono prose-code:text-sm prose-code:font-normal",
  "prose-pre:bg-background_alt prose-pre:p-4 prose-pre:text-sm prose-pre:font-light prose-pre:w-full prose-pre:my-2",
  "prose-table:text-primary prose-th:text-primary prose-td:text-primary prose-table:border-0",
].join(" ");

const PARAGRAPH_CLASS = {
  primary: "prose-p:text-primary",
  secondary: "prose-p:text-secondary",
  highlight: "prose-p:text-highlight",
};

interface MarkdownFormatProps {
  text?: string;
  variant?: "primary" | "secondary" | "highlight";
}

const MarkdownFormat: React.FC<MarkdownFormatProps> = ({
  text,
  variant = "primary",
}) => {
  if (!text) {
    return null;
  }

  const codeClass =
    variant === "primary" ? "prose-code:text-accent" : "prose-code:text-secondary";

  return (
    <div className={`${BASE_CLASSES} ${PARAGRAPH_CLASS[variant]} ${codeClass}`}>
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>{text.trim()}</ReactMarkdown>
    </div>
  );
};

export default MarkdownFormat;
