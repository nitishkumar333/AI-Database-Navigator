"use client";

import { createContext, useEffect, useRef, useState, useContext } from "react";
import { ToastContext } from "./ToastContext";
import { useDeviceId } from "@/app/getDeviceId";
import { QueryContext } from "./SocketContext";

export const SessionContext = createContext<{
  id: string | null;
  initialized: boolean;
  triggerFetchCollection: () => void;
  fetchCollectionFlag: boolean;
  unsavedChanges: boolean;
  updateUnsavedChanges: (unsaved: boolean) => void;
}>({
  id: "",
  initialized: false,
  triggerFetchCollection: () => {},
  fetchCollectionFlag: false,
  unsavedChanges: false,
  updateUnsavedChanges: () => {},
});

export const SessionProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { showSuccessToast } = useContext(ToastContext);
  const { backendOnline } = useContext(QueryContext);

  const id = useDeviceId();
  const initialized = useRef(false);
  const [fetchCollectionFlag, setFetchCollectionFlag] = useState(false);
  const [unsavedChanges, setUnsavedChanges] = useState(false);

  const triggerFetchCollection = () => {
    setFetchCollectionFlag((prev) => !prev);
  };

  const updateUnsavedChanges = (unsaved: boolean) => {
    setUnsavedChanges(unsaved);
  };

  useEffect(() => {
    if (initialized.current || !id || !backendOnline) return;
    initialized.current = true;
    showSuccessToast("Connected to SQLNav");
  }, [id, backendOnline]);

  return (
    <SessionContext.Provider
      value={{
        id,
        initialized: initialized.current,
        triggerFetchCollection,
        fetchCollectionFlag,
        unsavedChanges,
        updateUnsavedChanges,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
};
