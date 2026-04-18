"use client";

import React, { useContext } from "react";

import { AuthContext } from "./components/contexts/AuthContext";
import { RouterContext } from "./components/contexts/RouterContext";
import ChatPage from "./pages/ChatPage";
import CollectionPage from "./pages/CollectionPage";
import SettingsPage from "./pages/SettingsPage";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import LoginPage from "./pages/LoginPage";
import OnboardingPage from "./pages/OnboardingPage";
import { FaSpinner } from "react-icons/fa";

export default function Home() {
  const { isAuthenticated, isLoading, onboardingStatus } =
    useContext(AuthContext);
  const { currentPage } = useContext(RouterContext);

  // Show loading spinner while checking auth state
  if (isLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background z-50">
        <div className="flex flex-col items-center gap-4">
          <FaSpinner className="animate-spin text-accent" size={32} />
          <p className="text-muted-foreground text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  // Not authenticated → show Login page
  if (!isAuthenticated) {
    return <LoginPage />;
  }

  // Authenticated but onboarding incomplete → show Onboarding
  if (onboardingStatus && !onboardingStatus.onboarding_complete) {
    return <OnboardingPage />;
  }

  // Fully authenticated and onboarded -> show main app
  return (
    <>
      {currentPage === "chat" && <ChatPage />}
      {currentPage === "collection" && <CollectionPage />}
      {currentPage === "settings" && <SettingsPage />}
      {currentPage === "knowledge" && <KnowledgeBasePage />}
    </>
  );
}
