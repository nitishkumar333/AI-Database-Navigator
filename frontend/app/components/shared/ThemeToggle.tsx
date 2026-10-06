"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "../contexts/ThemeContext";
import { IoSunny, IoMoon, IoDesktopOutline } from "react-icons/io5";

interface ThemeToggleProps {
  variant?: "icon" | "pill" | "segmented";
  className?: string;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({
  variant = "icon",
  className = "",
  size = "md",
  showLabel = false,
}) => {
  const { theme, resolvedTheme, toggleTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = mounted ? resolvedTheme === "dark" : true;

  // Segmented control (Light / Dark / System)
  if (variant === "segmented") {
    const options: { id: "light" | "dark" | "system"; label: string; icon: React.ReactNode }[] = [
      { id: "light", label: "Light", icon: <IoSunny size={14} /> },
      { id: "dark", label: "Dark", icon: <IoMoon size={14} /> },
      { id: "system", label: "System", icon: <IoDesktopOutline size={14} /> },
    ];

    return (
      <div
        className={`flex items-center p-1 bg-background border border-foreground rounded-xl gap-1 ${className}`}
        role="radiogroup"
        aria-label="Theme selector"
      >
        {options.map((opt) => {
          const active = mounted ? theme === opt.id : opt.id === "dark";
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => setTheme(opt.id)}
              className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                active
                  ? "text-primary shadow-sm"
                  : "text-muted-foreground hover:text-primary hover:bg-foreground/50"
              }`}
            >
              {active && (
                <motion.div
                  layoutId="active-theme-pill"
                  className="absolute inset-0 bg-background_alt border border-foreground/60 rounded-lg shadow-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">{opt.icon}</span>
              <span className="relative z-10">{opt.label}</span>
            </button>
          );
        })}
      </div>
    );
  }

  // Pill switch variant
  if (variant === "pill") {
    return (
      <button
        type="button"
        id="theme-toggle-btn"
        onClick={toggleTheme}
        className={`relative inline-flex items-center h-8 w-16 px-1 rounded-full bg-background border border-foreground transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-accent/40 ${className}`}
        aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
        title={`Switch to ${isDark ? "light" : "dark"} mode`}
      >
        <span className="sr-only">Toggle theme</span>
        <div className="absolute inset-0 flex items-center justify-between px-2 text-xs text-muted-foreground pointer-events-none">
          <IoSunny size={13} className={isDark ? "opacity-30" : "opacity-0"} />
          <IoMoon size={12} className={isDark ? "opacity-0" : "opacity-30"} />
        </div>
        <motion.div
          className="w-6 h-6 rounded-full bg-background_alt border border-foreground/80 flex items-center justify-center text-primary shadow-sm"
          animate={{ x: isDark ? 32 : 0 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          {isDark ? (
            <IoMoon size={13} className="text-highlight" />
          ) : (
            <IoSunny size={14} className="text-amber-500" />
          )}
        </motion.div>
      </button>
    );
  }

  // Default: Icon button
  const iconSize = size === "sm" ? 14 : size === "lg" ? 18 : 16;
  const buttonDimensions =
    size === "sm"
      ? "w-7 h-7 p-1"
      : size === "lg"
      ? "w-9 h-9 p-2"
      : "w-8 h-8 p-1.5";

  return (
    <motion.button
      type="button"
      id="theme-toggle-btn"
      onClick={toggleTheme}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.92 }}
      className={`relative inline-flex items-center justify-center ${buttonDimensions} rounded-lg text-muted-foreground hover:text-primary hover:bg-foreground_alt border border-transparent hover:border-foreground/50 transition-all duration-200 ${className}`}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
    >
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.div
            key="moon"
            initial={{ rotate: -90, scale: 0, opacity: 0 }}
            animate={{ rotate: 0, scale: 1, opacity: 1 }}
            exit={{ rotate: 90, scale: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-center justify-center text-highlight"
          >
            <IoMoon size={iconSize} />
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ rotate: 90, scale: 0, opacity: 0 }}
            animate={{ rotate: 0, scale: 1, opacity: 1 }}
            exit={{ rotate: -90, scale: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-center justify-center text-amber-500"
          >
            <IoSunny size={iconSize} />
          </motion.div>
        )}
      </AnimatePresence>

      {showLabel && (
        <span className="ml-2 text-xs font-medium text-primary">
          {isDark ? "Dark" : "Light"}
        </span>
      )}
    </motion.button>
  );
};

export default ThemeToggle;
