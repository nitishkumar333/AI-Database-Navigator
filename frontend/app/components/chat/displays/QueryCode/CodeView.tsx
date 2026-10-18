"use client";

import { CodePayload } from "@/app/types/chat";
// The light build bundles only the languages registered below; the default
// build bundles every language Prism supports.
import SyntaxHighlighter from "react-syntax-highlighter/dist/esm/prism-light";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import oneDark from "react-syntax-highlighter/dist/esm/styles/prism/one-dark";
import oneLight from "react-syntax-highlighter/dist/esm/styles/prism/one-light";
import CopyToClipboardButton from "@/app/components/navigation/CopyButton";
import { useTheme } from "@/app/components/contexts/ThemeContext";

SyntaxHighlighter.registerLanguage("sql", sql);

interface CodeViewProps {
  code: CodePayload;
}

const CodeView: React.FC<CodeViewProps> = ({ code }) => {
  const { resolvedTheme } = useTheme();
  const isLight = resolvedTheme === "light";
  const background = isLight ? "#f8fafc" : "#141414";
  // Shown on one line: line breaks and the indentation around them become a
  // single space. The copy button keeps the query as the agent wrote it.
  const singleLine = (code?.text || "").replace(/\s*\r?\n\s*/g, " ").trim();

  return (
    <div className="flex flex-col overflow-hidden chat-animation">
      {/* One box: a toolbar with the copy button above the query. */}
      <div
        className="w-full overflow-hidden rounded-lg"
        style={{
          backgroundColor: background,
          border: `1px solid ${isLight ? "#cbd5e1" : "#2e2e2e"}`,
        }}
      >
        <div
          className="flex items-center justify-between pl-4 pr-1 py-0.5"
          style={{ borderBottom: `1px solid ${isLight ? "#e2e8f0" : "#232323"}` }}
        >
          <span className="text-xs uppercase tracking-wide text-secondary">
            {code?.language || "sql"}
          </span>
          <CopyToClipboardButton copyText={code?.text || ""} />
        </div>
        <SyntaxHighlighter
          language={code?.language || "sql"}
          // One unwrapped line; a long query scrolls sideways.
          wrapLongLines={false}
          style={isLight ? oneLight : oneDark}
          customStyle={{
            backgroundColor: background,
            color: isLight ? "#0f172a" : "#f2f2f2",
            border: "none",
            borderRadius: 0,
            margin: 0,
            width: "100%",
            overflowX: "auto",
            overflowY: "hidden",
          }}
          // The theme gives the inline <code> its own background (and, in
          // dark, a text shadow): behind wrapped text it looks like a
          // selection. Only the token colours are kept.
          codeTagProps={{ style: { background: "transparent", textShadow: "none" } }}
        >
          {singleLine || "No code available"}
        </SyntaxHighlighter>
      </div>
    </div>
  );
};

export default CodeView;
