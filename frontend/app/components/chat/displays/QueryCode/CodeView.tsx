"use client";

import { ResultPayload } from "@/app/types/chat";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Button } from "@/components/ui/button";
import CopyToClipboardButton from "@/app/components/navigation/CopyButton";
import { IoClose } from "react-icons/io5";
import { FaCode } from "react-icons/fa6";

interface CodeDisplayProps {
  /* eslint-disable @typescript-eslint/no-explicit-any */
  payload: ResultPayload[];
  handleViewChange: (
    view: "chat" | "code" | "result",
    payload: ResultPayload[] | null
  ) => void;
}

const CodeView: React.FC<CodeDisplayProps> = ({
  payload,
  handleViewChange,
}) => {
  console.log(payload, 'payload CodeView')
  if (!payload) return null;

  return (
    <div className="flex flex-col gap-2 overflow-hidden chat-animation">
      <div className="w-full flex justify-between items-center">
        <div className="flex gap-2 items-center">
          <p>Source Code</p>
        </div>
        <Button
          variant={"ghost"}
          className="text-secondary h-9 w-9"
          onClick={() => handleViewChange("chat", null)}
        >
          <IoClose size={12} />
        </Button>
      </div>
      {payload.map((item, index) => (
        <div key={index} className="w-full">
          <div className="relative">
            <div className="overflow-y-scroll">
              <div className="absolute top-2 right-0 p-3 flex gap-1">
                <CopyToClipboardButton copyText={(item.code?.text || item.metadata?.code?.text || '')} />
              </div>
              <SyntaxHighlighter
                language={item.code?.language || item.metadata?.code?.language || 'sql'}
                wrapLongLines={true}
                showLineNumbers={true}
                style={oneDark}
                customStyle={{
                  backgroundColor: "#202020",
                  color: "#f2f2f2",
                  width: "100%",
                  maxHeight: "calc(70vh - 2rem)",
                }}
                className="rounded-lg overflow-y-scroll"
              >
                {item.code?.text || item.metadata?.code?.text || 'No code available'}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default CodeView;
