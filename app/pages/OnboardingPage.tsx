"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AuthContext } from "../components/contexts/AuthContext";
import { ToastContext } from "../components/contexts/ToastContext";
import { host } from "../components/host";
import ConnectionForm from "../components/shared/ConnectionForm";
import KnowledgeBaseForm from "../components/shared/KnowledgeBaseForm";
import { GoCheck, GoDatabase } from "react-icons/go";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { MdChatBubbleOutline } from "react-icons/md";
import { FaSpinner } from "react-icons/fa";
import { IoCheckmarkCircle } from "react-icons/io5";

type Connection = {
  id: number;
  name: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
};

const steps = [
  {
    id: 1,
    label: "Connect Database",
    icon: GoDatabase,
    description: "Add your PostgreSQL database to start querying with natural language.",
  },
  {
    id: 2,
    label: "Knowledge Base",
    icon: HiOutlineBookOpen,
    description:
      "Select which tables the AI should know about to improve query accuracy.",
  },
  {
    id: 3,
    label: "Start Chatting",
    icon: MdChatBubbleOutline,
    description: "You're all set! Start asking questions about your data.",
  },
];

export default function OnboardingPage() {
  const { user, onboardingStatus, refreshOnboardingStatus } =
    useContext(AuthContext);
  const { showSuccessToast } = useContext(ToastContext);

  const [currentStep, setCurrentStep] = useState(1);
  const [savedConnectionId, setSavedConnectionId] = useState<number | null>(
    null
  );
  const [completing, setCompleting] = useState(false);

  // Determine starting step from onboarding status
  useEffect(() => {
    if (onboardingStatus) {
      if (onboardingStatus.has_connection && !onboardingStatus.has_knowledge_base) {
        setCurrentStep(2);
        // Fetch the user's first connection
        fetchFirstConnection();
      } else if (onboardingStatus.onboarding_complete) {
        setCurrentStep(3);
      }
    }
  }, [onboardingStatus]);

  const fetchFirstConnection = async () => {
    try {
      const token = localStorage.getItem("auth_token") || "";
      const response = await fetch(`${host}/api/connections`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const conns = await response.json();
        if (conns.length > 0) {
          setSavedConnectionId(conns[0].id);
        }
      }
    } catch {
      // ignore
    }
  };

  const handleConnectionSaved = async (connection: Connection) => {
    setSavedConnectionId(connection.id);
    await refreshOnboardingStatus();
    setCurrentStep(2);
  };

  const handleKnowledgeBaseCreated = async () => {
    await refreshOnboardingStatus();
    setCurrentStep(3);
  };

  const handleFinish = async () => {
    setCompleting(true);
    showSuccessToast("Setup Complete", "Welcome to AI Data Analyst!");
    // Small delay for the toast to show, then the page.tsx will detect onboarding_complete
    await refreshOnboardingStatus();
    setCompleting(false);
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-background z-50 overflow-y-auto py-8">
      {/* Subtle background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div
          className="absolute w-[800px] h-[800px] rounded-full opacity-[0.02]"
          style={{
            background:
              "radial-gradient(circle, hsl(151 46% 51%) 0%, transparent 70%)",
            top: "-300px",
            left: "50%",
            transform: "translateX(-50%)",
          }}
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="relative w-full max-w-2xl mx-4 flex flex-col gap-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center"
        >
          <h1 className="text-3xl font-bold text-primary font-heading">
            Welcome{user?.username ? `, ${user.username}` : ""}! 👋
          </h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Let&apos;s get your workspace set up in a few quick steps.
          </p>
        </motion.div>

        {/* Stepper */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="flex items-center justify-center gap-0"
        >
          {steps.map((step, index) => {
            const isCompleted = currentStep > step.id;
            const isActive = currentStep === step.id;
            const Icon = step.icon;

            return (
              <React.Fragment key={step.id}>
                {index > 0 && (
                  <div
                    className={`h-[2px] w-12 sm:w-20 transition-colors duration-500 ${
                      currentStep > step.id
                        ? "bg-accent"
                        : "bg-foreground/40"
                    }`}
                  />
                )}
                <div className="flex flex-col items-center gap-2">
                  <motion.div
                    className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-all duration-500 border ${
                      isCompleted
                        ? "bg-accent/20 border-accent text-accent"
                        : isActive
                          ? "bg-accent/10 border-accent/60 text-accent shadow-lg shadow-accent/10"
                          : "bg-foreground/20 border-foreground/40 text-muted-foreground"
                    }`}
                    animate={isActive ? { scale: [1, 1.05, 1] } : {}}
                    transition={{
                      duration: 2,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                  >
                    {isCompleted ? (
                      <IoCheckmarkCircle size={24} />
                    ) : (
                      <Icon size={22} />
                    )}
                  </motion.div>
                  <span
                    className={`text-[11px] font-medium text-center transition-colors duration-300 hidden sm:block ${
                      isActive || isCompleted
                        ? "text-primary"
                        : "text-muted-foreground"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              </React.Fragment>
            );
          })}
        </motion.div>

        {/* Step Content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.98 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className="w-full"
          >
            {/* Step description header */}
            <div className="mb-4 text-center">
              <h2 className="text-lg font-semibold text-primary">
                Step {currentStep}: {steps[currentStep - 1].label}
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                {steps[currentStep - 1].description}
              </p>
            </div>

            {/* Step 1: Add Connection */}
            {currentStep === 1 && (
              <ConnectionForm
                onConnectionSaved={handleConnectionSaved}
                compact
              />
            )}

            {/* Step 2: Create Knowledge Base */}
            {currentStep === 2 && savedConnectionId && (
              <KnowledgeBaseForm
                connectionId={savedConnectionId}
                onKnowledgeBaseCreated={handleKnowledgeBaseCreated}
                compact
              />
            )}

            {/* Step 3: All Done */}
            {currentStep === 3 && (
              <div className="flex flex-col items-center justify-center gap-6 p-12 rounded-2xl border border-accent/30 bg-accent/5">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{
                    type: "spring",
                    stiffness: 200,
                    damping: 15,
                    delay: 0.1,
                  }}
                  className="w-20 h-20 rounded-full bg-accent/20 border-2 border-accent flex items-center justify-center"
                >
                  <GoCheck className="text-accent" size={40} />
                </motion.div>
                <div className="text-center">
                  <h3 className="text-xl font-bold text-primary">
                    You&apos;re all set! 🎉
                  </h3>
                  <p className="text-muted-foreground text-sm mt-2">
                    Your database is connected and knowledge base is ready.
                    <br />
                    Start asking questions about your data in natural language.
                  </p>
                </div>
                <motion.button
                  onClick={handleFinish}
                  disabled={completing}
                  className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-accent to-accent/80 text-background font-semibold text-sm hover:shadow-lg hover:shadow-accent/20 disabled:opacity-50 transition-all duration-300 flex items-center gap-2"
                  whileHover={{ scale: completing ? 1 : 1.02 }}
                  whileTap={{ scale: completing ? 1 : 0.98 }}
                >
                  {completing ? (
                    <FaSpinner className="animate-spin" size={16} />
                  ) : (
                    <>
                      <MdChatBubbleOutline size={18} />
                      Start Chatting
                    </>
                  )}
                </motion.button>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
