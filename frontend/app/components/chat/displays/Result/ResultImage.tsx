"use client";

import React, { useState } from "react";
import { PiImageBroken } from "react-icons/pi";
import { Skeleton } from "@/components/ui/skeleton";
import { safeUrl } from "@/app/utils/formatValue";

interface ResultImageProps {
  src: unknown;
  alt: string;
  className?: string;
  // object-cover crops to fill; object-contain shows the whole picture.
  fit?: "cover" | "contain";
}

/**
 * An image from a result row. Loads lazily, sends no referrer (some hosts
 * block hotlinking by referrer, and it leaks the app's URL), shows a skeleton
 * while loading and a placeholder when the URL is missing or fails.
 */
const ResultImage: React.FC<ResultImageProps> = ({ src, alt, className = "", fit = "cover" }) => {
  const url = safeUrl(src);
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");

  return (
    <div className={`relative overflow-hidden bg-secondary/5 ${className}`}>
      {url && state === "loading" && <Skeleton className="absolute inset-0 w-full h-full" />}
      {url && state !== "error" ? (
        // eslint-disable-next-line @next/next/no-img-element -- arbitrary hosts; next/image needs them configured
        <img
          src={url}
          alt={alt}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setState("loaded")}
          onError={() => setState("error")}
          className={`w-full h-full transition-opacity duration-300 ${
            fit === "cover" ? "object-cover" : "object-contain"
          } ${state === "loaded" ? "opacity-100" : "opacity-0"}`}
        />
      ) : (
        <div
          className="absolute inset-0 flex items-center justify-center text-secondary/60"
          title="Image unavailable"
        >
          <PiImageBroken className="w-1/3 h-1/3 max-w-8 max-h-8" aria-hidden />
          <span className="sr-only">Image unavailable</span>
        </div>
      )}
    </div>
  );
};

export default ResultImage;
