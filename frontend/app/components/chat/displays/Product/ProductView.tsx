"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { Skeleton } from "@/components/ui/skeleton";

// Internal keys that shouldn't be rendered as visible fields
const HIDDEN_KEYS = new Set([
  "uuid",
  "E_SUMMARY",
  "_REF_ID",
  "_additional",
]);

// Keys that are used for the hero section (image / title) and handled specially
const HERO_KEYS = new Set(["image", "name", "title"]);

interface ProductViewProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  product: Record<string, any>;
}

/**
 * Formats a raw key string into a human-readable label.
 * e.g. "product_id" → "Product Id", "subcategory" → "Subcategory"
 */
const formatLabel = (key: string): string =>
  key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

/**
 * Try to format a number as currency if it looks like a price.
 */
const formatPrice = (value: number): string =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);

const isPriceKey = (key: string): boolean =>
  /price|cost|amount|msrp/i.test(key);

const isRatingKey = (key: string): boolean =>
  /rating|score|stars/i.test(key);

const isImageUrl = (value: string): boolean =>
  /\.(jpg|jpeg|png|gif|webp|svg|avif|bmp)(\?.*)?$/i.test(value) ||
  value.startsWith("data:image");

const isUrl = (value: string): boolean => {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
};

/** Renders 0-5 stars for a numeric rating */
const RatingStars: React.FC<{ rating: number }> = ({ rating }) => (
  <div className="flex items-center gap-2">
    <div className="flex items-center">
      {Array.from({ length: 5 }, (_, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5 + i * 0.05, duration: 0.2 }}
          className={`text-sm transition-colors duration-200 ${
            i < Math.round(rating) ? "text-alt_color_b" : "text-secondary/30"
          }`}
        >
          ★
        </motion.span>
      ))}
    </div>
    <span className="text-sm text-secondary/70 font-light">
      {rating.toFixed(1)}
    </span>
  </div>
);

// ─── Value renderer ────────────────────────────────────────────────────────────

interface FieldValueProps {
  fieldKey: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  value: any;
}

const FieldValue: React.FC<FieldValueProps> = ({ fieldKey, value }) => {
  // --- Arrays → tag pills --------------------------------------------------
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return (
      <div className="flex flex-wrap gap-2">
        {value.map((item, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.06, duration: 0.3 }}
            className="px-4 py-2 bg-secondary/5 text-secondary/70 text-sm rounded-full border border-secondary/10 hover:bg-secondary/10 hover:border-secondary/20 transition-all duration-300"
          >
            {String(item)}
          </motion.span>
        ))}
      </div>
    );
  }

  // --- Numbers ---------------------------------------------------------------
  if (typeof value === "number") {
    if (isRatingKey(fieldKey)) return <RatingStars rating={value} />;
    if (isPriceKey(fieldKey))
      return (
        <span className="text-3xl lg:text-4xl text-primary font-thin tracking-tighter">
          {formatPrice(value)}
        </span>
      );
    return (
      <span className="text-lg text-primary font-light">{value}</span>
    );
  }

  // --- Booleans --------------------------------------------------------------
  if (typeof value === "boolean") {
    return (
      <span
        className={`text-sm font-medium px-3 py-1 rounded-full ${
          value
            ? "bg-green-500/10 text-green-400 border border-green-500/20"
            : "bg-red-500/10 text-red-400 border border-red-500/20"
        }`}
      >
        {value ? "Yes" : "No"}
      </span>
    );
  }

  // --- Strings ---------------------------------------------------------------
  if (typeof value === "string") {
    if (!value.trim()) return null;

    // Render inline images
    if (isImageUrl(value)) {
      return (
        <img
          src={value}
          alt={fieldKey}
          className="max-h-40 rounded-xl object-cover border border-secondary/10"
        />
      );
    }

    // Render links
    if (isUrl(value)) {
      return (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="text-alt_color_a hover:underline break-all text-sm"
        >
          {value}
        </a>
      );
    }

    // Long text → paragraph style
    if (value.length > 120) {
      return (
        <p className="text-base text-secondary font-light leading-relaxed">
          {value}
        </p>
      );
    }

    return (
      <span className="text-lg text-primary font-light">{value}</span>
    );
  }

  // --- Objects / fallback ----------------------------------------------------
  if (typeof value === "object" && value !== null) {
    return (
      <pre className="text-xs text-secondary/70 bg-secondary/5 rounded-lg p-3 overflow-x-auto border border-secondary/10">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }

  return null;
};

// ─── Main component ────────────────────────────────────────────────────────────

const ProductView: React.FC<ProductViewProps> = ({ product }) => {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  // Derive the "title" and "image" from common key names
  const displayName =
    product.name || product.title || product.product_name || "Product";
  const displayImage = product.image || product.image_url || product.thumbnail;
  const displayBrand = product.brand || product.manufacturer || product.vendor;

  // Collect remaining fields, split into "highlight" (short) and "detail" (long / arrays)
  const { highlightFields, detailFields } = useMemo(() => {
    const highlights: { key: string; value: unknown }[] = [];
    const details: { key: string; value: unknown }[] = [];

    for (const [key, value] of Object.entries(product)) {
      if (HIDDEN_KEYS.has(key) || HERO_KEYS.has(key)) continue;
      // Skip keys already consumed by the hero section
      if (
        ["brand", "manufacturer", "vendor", "image_url", "thumbnail", "product_name", "title"].includes(key)
      )
        continue;
      if (value === null || value === undefined || value === "") continue;

      const isLong =
        Array.isArray(value) ||
        (typeof value === "string" && value.length > 120) ||
        (typeof value === "object" && !Array.isArray(value));

      if (isLong) {
        details.push({ key, value });
      } else {
        highlights.push({ key, value });
      }
    }

    return { highlightFields: highlights, detailFields: details };
  }, [product]);

  return (
    <motion.div
      className="w-full max-w-4xl mx-auto"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className="space-y-8">
        {/* ─── Hero Image ──────────────────────────────────────────────── */}
        {displayImage && (
          <motion.div
            className="relative w-full h-[60vh] lg:h-[70vh] overflow-hidden rounded-3xl bg-gradient-to-br from-secondary/3 to-secondary/8 shadow-2xl shadow-black/10"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              delay: 0.2,
              duration: 0.8,
              ease: [0.25, 0.46, 0.45, 0.94],
            }}
          >
            {!imageLoaded && !imageError && (
              <Skeleton className="absolute inset-0 w-full h-full rounded-3xl" />
            )}

            {!imageError && (
              <motion.img
                src={displayImage}
                alt={displayName}
                className={`w-full h-full object-cover transition-transform duration-1000 ease-out hover:scale-105 ${
                  imageLoaded ? "opacity-100" : "opacity-0"
                }`}
                onLoad={() => setImageLoaded(true)}
                onError={() => {
                  setImageError(true);
                  setImageLoaded(true);
                }}
                loading="lazy"
              />
            )}

            {imageError && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-secondary/30 text-center p-8">
                  <div className="text-6xl mb-4 opacity-50">📷</div>
                  <div className="text-sm opacity-60">Image unavailable</div>
                </div>
              </div>
            )}

            {/* Gradient overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />

            {/* Overlay text */}
            <div className="absolute inset-0 flex flex-col justify-end p-8 lg:p-12">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.8 }}
                className="text-white space-y-3"
              >
                {displayBrand && (
                  <p className="text-sm opacity-80 uppercase tracking-[0.25em] font-medium">
                    {displayBrand}
                  </p>
                )}
                <h1 className="text-4xl lg:text-5xl xl:text-6xl font-extralight leading-[0.9] tracking-tight">
                  {displayName}
                </h1>
              </motion.div>
            </div>
          </motion.div>
        )}

        {/* ─── Title fallback when no image ────────────────────────── */}
        {!displayImage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="space-y-2"
          >
            {displayBrand && (
              <p className="text-sm text-secondary/60 uppercase tracking-[0.25em] font-medium">
                {displayBrand}
              </p>
            )}
            <h1 className="text-4xl lg:text-5xl font-extralight text-primary tracking-tight">
              {displayName}
            </h1>
          </motion.div>
        )}

        {/* ─── Highlight fields (grid) ─────────────────────────────── */}
        {highlightFields.length > 0 && (
          <motion.div
            className={`grid gap-8 py-8 border-y border-secondary/10 ${
              highlightFields.length === 1
                ? "grid-cols-1"
                : highlightFields.length === 2
                ? "grid-cols-1 sm:grid-cols-2"
                : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
            }`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.6 }}
          >
            {highlightFields.map(({ key, value }, i) => (
              <motion.div
                key={key}
                className="text-center space-y-3"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.08, duration: 0.4 }}
              >
                <div className="text-xs text-secondary/40 uppercase tracking-[0.2em] font-medium">
                  {formatLabel(key)}
                </div>
                <div className="flex justify-center">
                  <FieldValue fieldKey={key} value={value} />
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}

        {/* ─── Detail fields (stacked) ─────────────────────────────── */}
        {detailFields.length > 0 && (
          <motion.div
            className="space-y-8 px-4 lg:px-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, duration: 0.6 }}
          >
            {detailFields.map(({ key, value }, i) => (
              <motion.div
                key={key}
                className="space-y-3"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7 + i * 0.1, duration: 0.5 }}
              >
                <div className="text-xs text-secondary/40 uppercase tracking-[0.2em] font-medium">
                  {formatLabel(key)}
                </div>
                <FieldValue fieldKey={key} value={value} />
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>
    </motion.div>
  );
};

export default ProductView;
