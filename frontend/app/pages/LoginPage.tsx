"use client";

import React, { useState, useContext } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AuthContext } from "../components/contexts/AuthContext";
import { GoDatabase } from "react-icons/go";
import { FaSpinner } from "react-icons/fa";
import {
  IoMailOutline,
  IoPersonOutline,
  IoLockClosedOutline,
  IoEyeOutline,
  IoEyeOffOutline,
} from "react-icons/io5";

export default function LoginPage() {
  const { login, register } = useContext(AuthContext);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    let result;
    if (mode === "login") {
      result = await login(email, password);
    } else {
      if (!username.trim()) {
        setError("Username is required");
        setLoading(false);
        return;
      }
      result = await register(email, username, password);
    }

    if (!result.ok) {
      setError(result.error || "Something went wrong");
    }
    setLoading(false);
  };

  const switchMode = () => {
    setMode(mode === "login" ? "register" : "login");
    setError("");
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-background z-50 overflow-hidden">
      {/* Animated background gradient orbs */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute w-[600px] h-[600px] rounded-full opacity-[0.03]"
          style={{
            background:
              "radial-gradient(circle, hsl(151 46% 51%) 0%, transparent 70%)",
            top: "-200px",
            right: "-100px",
          }}
          animate={{
            scale: [1, 1.2, 1],
            x: [0, 30, 0],
            y: [0, -20, 0],
          }}
          transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full opacity-[0.03]"
          style={{
            background:
              "radial-gradient(circle, hsl(202 54% 59%) 0%, transparent 70%)",
            bottom: "-150px",
            left: "-100px",
          }}
          animate={{
            scale: [1.2, 1, 1.2],
            x: [0, -20, 0],
            y: [0, 30, 0],
          }}
          transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="relative w-full max-w-md mx-4"
      >
        {/* Card */}
        <div className="relative overflow-hidden rounded-2xl border-foreground/60 backdrop-blur-xl shadow-black/30">
          {/* Accent top bar */}
          <div className="h-1 w-full bg-gradient-to-r from-accent via-highlight to-accent" />

          <div className="p-8 md:p-10">
            {/* Logo & Title */}
            <motion.div
              className="flex flex-col items-center gap-3 mb-8"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent/20 to-highlight/20 border border-accent/30 flex items-center justify-center shadow-lg shadow-accent/10">
                <GoDatabase className="text-accent" size={28} />
              </div>
              <div className="text-center">
                <h1 className="text-2xl font-bold text-primary font-heading">
                  SQLNav
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Natural Language → SQL Platform
                </p>
              </div>
            </motion.div>

            {/* Mode tabs */}
            <div className="flex rounded-xl bg-background/60 p-1 mb-6 border border-foreground/30">
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
                className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-300 ${
                  mode === "login"
                    ? "bg-foreground/50 text-primary shadow-sm"
                    : "text-muted-foreground hover:text-primary"
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("register");
                  setError("");
                }}
                className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-300 ${
                  mode === "register"
                    ? "bg-foreground/50 text-primary shadow-sm"
                    : "text-muted-foreground hover:text-primary"
                }`}
              >
                Create Account
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <AnimatePresence mode="wait">
                <motion.div
                  key={mode}
                  initial={{ opacity: 0, x: mode === "register" ? 20 : -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: mode === "register" ? -20 : 20 }}
                  transition={{ duration: 0.25 }}
                  className="flex flex-col gap-4"
                >
                  {/* Email */}
                  <div className="relative">
                    <IoMailOutline
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
                      size={18}
                    />
                    <input
                      id="login-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Email address"
                      required
                      className="w-full pl-11 pr-4 py-3 bg-background border border-foreground/50 rounded-xl text-sm text-primary placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent/50 transition-all"
                    />
                  </div>

                  {/* Username (register only) */}
                  {mode === "register" && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="relative"
                    >
                      <IoPersonOutline
                        className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
                        size={18}
                      />
                      <input
                        id="register-username"
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="Username"
                        required
                        className="w-full pl-11 pr-4 py-3 bg-background border border-foreground/50 rounded-xl text-sm text-primary placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent/50 transition-all"
                      />
                    </motion.div>
                  )}

                  {/* Password */}
                  <div className="relative">
                    <IoLockClosedOutline
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
                      size={18}
                    />
                    <input
                      id="login-password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Password"
                      required
                      minLength={6}
                      className="w-full pl-11 pr-12 py-3 bg-background border border-foreground/50 rounded-xl text-sm text-primary placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent/50 transition-all"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary transition-colors"
                    >
                      {showPassword ? (
                        <IoEyeOffOutline size={18} />
                      ) : (
                        <IoEyeOutline size={18} />
                      )}
                    </button>
                  </div>
                </motion.div>
              </AnimatePresence>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
                  >
                    {error}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Submit */}
              <motion.button
                type="submit"
                disabled={loading}
                className="w-full tracking-wider py-3.5 rounded-xl bg-gradient-to-r from-accent to-accent/80 text-background font-semibold text-sm hover:shadow-lg hover:shadow-accent/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2"
                whileHover={{ scale: loading ? 1 : 1.01 }}
                whileTap={{ scale: loading ? 1 : 0.99 }}
              >
                {loading ? (
                  <FaSpinner className="animate-spin" size={16} />
                ) : mode === "login" ? (
                  "SIGN IN"
                ) : (
                  "CREATE ACCOUNT"
                )}
              </motion.button>
            </form>

            {/* Switch mode link */}
            <p className="text-center text-sm text-muted-foreground mt-6">
              {mode === "login"
                ? "Don't have an account? "
                : "Already have an account? "}
              <button
                type="button"
                onClick={switchMode}
                className="text-accent hover:text-accent/80 font-medium transition-colors"
              >
                {mode === "login" ? "Create one" : "Sign in"}
              </button>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
