"use client";

import { CodePayload } from "@/app/types/chat";
// The light build bundles only the languages registered below; the default
// build bundles every language Prism supports.
import SyntaxHighlighter from "react-syntax-highlighter/dist/esm/prism-light";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import oneDark from "react-syntax-highlighter/dist/esm/styles/prism/one-dark";
import oneLight from "react-syntax-highlighter/dist/esm/styles/prism/one-light";
import { Button } from "@/components/ui/button";
import CopyToClipboardButton from "@/app/components/navigation/CopyButton";
import { IoClose } from "react-icons/io5";
import { FaCode } from "react-icons/fa6";
import { useTheme } from "@/app/components/contexts/ThemeContext";

SyntaxHighlighter.registerLanguage("sql", sql);

interface CodeViewProps {
  code: CodePayload;
  onClose: () => void;
}

const CodeView: React.FC<CodeViewProps> = ({ code, onClose }) => {
  const { resolvedTheme } = useTheme();
  const isLight = resolvedTheme === "light";

  return (
    <div className="flex flex-col gap-2 overflow-hidden chat-animation">
      <div className="w-full flex justify-between items-center">
        <div className="flex gap-2 items-center">
          <div className="flex items-center gap-2">
            <FaCode size={14} className="text-highlight flex-shrink-0" />
            <p className="text-secondary text-sm">Source Code</p>
          </div>
        </div>
        <Button
          variant={"ghost"}
          className="text-secondary h-9 w-9"
          onClick={onClose}
        >
          <IoClose size={12} />
        </Button>
      </div>
      <div className="w-full">
        <div className="flex">
          <SyntaxHighlighter
            language={code?.language || "sql"}
            wrapLongLines={true}
            showLineNumbers={true}
            style={isLight ? oneLight : oneDark}
            customStyle={{
              backgroundColor: isLight ? "#f8fafc" : "#141414",
              color: isLight ? "#0f172a" : "#f2f2f2",
              border: isLight ? "1px solid #cbd5e1" : "1px solid #2e2e2e",
              width: "100%",
              overflowX: "auto",
              overflowY: "hidden",
            }}
            className="rounded-lg"
          >
            {code?.text || "No code available"}
          </SyntaxHighlighter>
          <div className="flex items-center ml-2">
            <CopyToClipboardButton copyText={code?.text || ""} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default CodeView;
