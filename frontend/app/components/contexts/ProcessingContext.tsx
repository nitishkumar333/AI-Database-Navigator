"use client";

import { createContext } from "react";

// Processing context is no longer used (WebSocket removal)
// Kept as empty provider for any remaining imports

export const ProcessingContext = createContext<{}>({});

export const ProcessingProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  return (
    <ProcessingContext.Provider value={{}}>
      {children}
    </ProcessingContext.Provider>
  );
};
