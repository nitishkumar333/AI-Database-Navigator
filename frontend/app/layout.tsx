import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import { Manrope, Space_Grotesk } from "next/font/google";
import { AuthProvider } from "./components/contexts/AuthContext";
import { SessionProvider } from "./components/contexts/SessionContext";
import SidebarComponent from "./components/navigation/SidebarComponent";
import { CollectionProvider } from "./components/contexts/CollectionContext";
import { ConversationProvider } from "./components/contexts/ConversationContext";
import { QueryProvider } from "./components/contexts/SocketContext";
import { ToastProvider } from "./components/contexts/ToastContext";

import { Toaster } from "@/components/ui/toaster";

import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { RouterProvider } from "./components/contexts/RouterContext";

import { ThemeProvider } from "./components/contexts/ThemeContext";

const space_grotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-text",
  weight: ["300", "400", "500", "600", "700"],
});

const manrope = Manrope({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-heading",
  weight: ["200", "300", "400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "SQLNav",
  description: "Natural Language → SQL Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="dark">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var stored = localStorage.getItem('theme');
                  var isDark = true;
                  if (stored === 'light') {
                    isDark = false;
                  } else if (stored === 'system') {
                    isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                  } else if (stored === 'dark') {
                    isDark = true;
                  }
                  var root = document.documentElement;
                  if (isDark) {
                    root.classList.add('dark');
                    root.classList.remove('light');
                    root.setAttribute('data-theme', 'dark');
                    root.style.colorScheme = 'dark';
                  } else {
                    root.classList.remove('dark');
                    root.classList.add('light');
                    root.setAttribute('data-theme', 'light');
                    root.style.colorScheme = 'light';
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <body
        className={`bg-background h-screen w-screen overflow-hidden ${space_grotesk.variable} ${manrope.variable} font-text antialiased flex transition-colors duration-200`}
      >
        <Suspense fallback={<div></div>}>
          <ThemeProvider>
            <ToastProvider>
              <AuthProvider>
                <RouterProvider>
                  <QueryProvider>
                    <SessionProvider>
                      <CollectionProvider>
                        <ConversationProvider>
                          <SidebarProvider>
                            <SidebarComponent />
                            <main className="flex flex-1 min-w-0 flex-col md:flex-row w-full gap-2 md:gap-6 items-start justify-start p-2 pt-0 md:p-6 md:pt-1 overflow-hidden">
                              <SidebarTrigger className="lg:hidden flex text-secondary hover:text-primary hover:bg-foreground_alt z-50" />
                              {children}
                            </main>
                          </SidebarProvider>
                          <Toaster />
                        </ConversationProvider>
                      </CollectionProvider>
                    </SessionProvider>
                  </QueryProvider>
                </RouterProvider>
              </AuthProvider>
            </ToastProvider>
          </ThemeProvider>
        </Suspense>
      </body>
    </html>
  );
}
