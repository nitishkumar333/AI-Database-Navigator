import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { IoCheckmarkOutline } from "react-icons/io5";
import { MdContentCopy } from "react-icons/md";

interface CopyToClipboardProps {
  copyText: string;
}

const CopyToClipboardButton: React.FC<CopyToClipboardProps> = ({
  copyText,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(copyText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Button
      onClick={handleCopy}
      variant="ghost"
      className={`${copied ? "text-accent" : "text-secondary"} h-9 w-9`}
      title="Copy to clipboard"
    >
      {copied ? <IoCheckmarkOutline size={14} /> : <MdContentCopy size={14} />}
    </Button>
  );
};

export default CopyToClipboardButton;
