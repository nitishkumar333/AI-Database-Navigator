"use client";

export const host =
  process.env.NEXT_PUBLIC_IS_STATIC !== "true" ? "http://localhost:8000" : "";

export const public_path =
  process.env.NEXT_PUBLIC_IS_STATIC !== "true" ? "/" : "/static/";
