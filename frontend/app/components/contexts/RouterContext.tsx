"use client";

import { createContext, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const VALID_PAGES = ["chat", "collection", "settings", "knowledge"];

type Params = Record<string, string>;

export const RouterContext = createContext<{
  currentPage: string;
  changePage: (page: string, params?: Params, replace?: boolean) => void;
}>({
  currentPage: "chat",
  changePage: () => {},
});

export const RouterProvider = ({ children }: { children: React.ReactNode }) => {
  const [currentPage, setCurrentPage] = useState<string>("chat");

  const searchParams = useSearchParams();

  const currentParams = (): Params => Object.fromEntries(searchParams.entries());

  const changePage = (page: string, params: Params = {}, replace: boolean = false) => {
    const finalParams = replace
      ? { page, ...params }
      : { ...currentParams(), page, ...params };

    const url = `/?${new URLSearchParams(finalParams).toString()}`;

    if (replace) {
      window.history.replaceState(null, "", url);
    } else {
      window.history.pushState(null, "", url);
    }
  };

  useEffect(() => {
    const pageParam = searchParams.get("page");

    // No page parameter: go to the chat page, keeping any other parameters
    // (like conversation).
    if (!pageParam) {
      const url = `/?${new URLSearchParams({ page: "chat", ...currentParams() }).toString()}`;
      window.history.replaceState(null, "", url);
      setCurrentPage("chat");
      return;
    }

    // Unknown page: go to the chat page instead.
    if (!VALID_PAGES.includes(pageParam)) {
      const { page: _page, ...rest } = currentParams(); // eslint-disable-line @typescript-eslint/no-unused-vars
      const url = `/?${new URLSearchParams({ page: "chat", ...rest }).toString()}`;
      window.history.replaceState(null, "", url);
      setCurrentPage("chat");
      return;
    }

    setCurrentPage(pageParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <RouterContext.Provider value={{ currentPage, changePage }}>
      {children}
    </RouterContext.Provider>
  );
};
