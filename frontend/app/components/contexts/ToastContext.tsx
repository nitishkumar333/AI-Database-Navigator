"use client";

import { createContext, useState, useCallback } from "react";
import { useToast } from "@/hooks/useToast";
import { MdContentCopy } from "react-icons/md";
import { IoCheckmarkOutline } from "react-icons/io5";
import { Button } from "@/components/ui/button";

// Component for error toast actions with copy and close buttons
const ErrorToastActions: React.FC<{ errorText: string }> = ({ errorText }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(errorText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy error text:", err);
    }
  };

  return (
    <div className="flex gap-2">
      <Button
        onClick={handleCopy}
        variant="ghost"
        size="sm"
        className="h-8 shrink-0 px-3 text-sm font-medium transition-colors hover:bg-secondary focus:outline-none focus:ring-1 focus:ring-ring group-[.destructive]:hover:border-destructive/30 group-[.destructive]:hover:bg-destructive group-[.destructive]:hover:text-destructive-foreground group-[.destructive]:focus:ring-destructive"
        title="Copy error to clipboard"
      >
        {copied ? (
          <IoCheckmarkOutline className="h-4 w-4" />
        ) : (
          <MdContentCopy className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
};

export const ToastContext = createContext<{
  showErrorToast: (title: string, description?: string) => void;
  showSuccessToast: (title: string, description?: string) => void;
}>({
  showErrorToast: () => {},
  showSuccessToast: () => {},
});

export const ToastProvider = ({ children }: { children: React.ReactNode }) => {
  const { toast } = useToast();

  const showErrorToast = useCallback(
    (title: string, description?: string) => {
      const errorText = description || "An error occurred. Please try again.";
      const fullErrorText = `${title}: ${errorText}`;

      toast({
        title,
        description: errorText,
        variant: "destructive",
        action: <ErrorToastActions errorText={fullErrorText} />,
      });
    },
    [toast]
  );

  const showSuccessToast = useCallback(
    (title: string, description?: string) => {
      toast({
        title,
        description,
        variant: "default",
      });
    },
    [toast]
  );

  return (
    <ToastContext.Provider value={{ showErrorToast, showSuccessToast }}>
      {children}
    </ToastContext.Provider>
  );
};
