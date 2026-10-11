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

// Max tags shown per array field, so the modal always fits on screen
const MAX_TAGS = 8;

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
  <div className="flex items-center gap-1.5">
    <div className="flex items-center">
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={`text-sm ${
            i < Math.round(rating) ? "text-alt_color_b" : "text-secondary/30"
          }`}
        >
          ★
        </span>
      ))}
    </div>
    <span className="text-xs text-secondary">{rating.toFixed(1)}</span>
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
    const hidden = value.length - MAX_TAGS;
    return (
      <div className="flex flex-wrap gap-1.5">
        {value.slice(0, MAX_TAGS).map((item, i) => (
          <span
            key={i}
            className="px-2.5 py-0.5 bg-secondary/5 text-secondary text-xs rounded-full border border-secondary/10"
          >
            {String(item)}
          </span>
        ))}
        {hidden > 0 && (
          <span className="px-2.5 py-0.5 text-secondary/60 text-xs">
            +{hidden} more
          </span>
        )}
      </div>
    );
  }

  // --- Numbers ---------------------------------------------------------------
  if (typeof value === "number") {
    if (isRatingKey(fieldKey)) return <RatingStars rating={value} />;
    if (isPriceKey(fieldKey))
      return (
        <span className="text-lg text-primary font-medium">
          {formatPrice(value)}
        </span>
      );
    return <span className="text-sm text-primary">{value}</span>;
  }

  // --- Booleans --------------------------------------------------------------
  if (typeof value === "boolean") {
    return (
      <span
        className={`text-xs font-medium px-2 py-0.5 rounded-full ${
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
          className="h-16 rounded-lg object-cover border border-secondary/10"
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
          title={value}
          className="block text-alt_color_a hover:underline truncate text-sm"
        >
          {value}
        </a>
      );
    }

    // Long text → clamped paragraph (full text on hover)
    if (value.length > 120) {
      return (
        <p
          title={value}
          className="text-sm text-secondary leading-relaxed line-clamp-4"
        >
          {value}
        </p>
      );
    }

    return (
      <span title={value} className="block text-sm text-primary truncate">
        {value}
      </span>
    );
  }

  // --- Objects / fallback ----------------------------------------------------
  if (typeof value === "object" && value !== null) {
    return (
      <pre className="text-[11px] text-secondary bg-secondary/5 rounded-lg p-2 max-h-24 overflow-hidden whitespace-pre-wrap break-all border border-secondary/10">
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
      className="flex flex-col md:flex-row w-full max-h-[90vh] overflow-hidden"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      {/* ─── Image ──────────────────────────────────────────────────── */}
      {displayImage && (
        <div className="relative shrink-0 w-full h-[28vh] md:h-auto md:w-2/5 md:min-h-[360px] md:max-h-[90vh] bg-secondary/5">
          {!imageLoaded && !imageError && (
            <Skeleton className="absolute inset-0 w-full h-full rounded-none" />
          )}

          {!imageError && (
            <img
              src={displayImage}
              alt={displayName}
              className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${
                imageLoaded ? "opacity-100" : "opacity-0"
              }`}
              onLoad={() => setImageLoaded(true)}
              onError={() => {
                setImageError(true);
                setImageLoaded(true);
              }}
            />
          )}

          {imageError && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-secondary/40">
              <div className="text-4xl mb-2 opacity-50">📷</div>
              <div className="text-xs">Image unavailable</div>
            </div>
          )}
        </div>
      )}

      {/* ─── Details ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 min-w-0 flex-1 p-5 md:p-6 overflow-hidden">
        {/* Title (right padding keeps clear of the dialog close button) */}
        <div className="space-y-1 pr-8">
          {displayBrand && (
            <p className="text-xs text-secondary uppercase tracking-[0.2em] font-medium truncate">
              {displayBrand}
            </p>
          )}
          <h2
            title={displayName}
            className="text-xl md:text-2xl font-light text-primary leading-tight line-clamp-2"
          >
            {displayName}
          </h2>
        </div>

        {/* Highlight fields (compact grid) */}
        {highlightFields.length > 0 && (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3 py-4 border-y border-secondary/10">
            {highlightFields.map(({ key, value }) => (
              <div key={key} className="min-w-0 space-y-1">
                <div className="text-[10px] text-secondary/60 uppercase tracking-[0.15em] font-medium truncate">
                  {formatLabel(key)}
                </div>
                <FieldValue fieldKey={key} value={value} />
              </div>
            ))}
          </div>
        )}

        {/* Detail fields (stacked) */}
        {detailFields.length > 0 && (
          <div className="flex flex-col gap-3 min-h-0">
            {detailFields.map(({ key, value }) => (
              <div key={key} className="min-w-0 space-y-1.5">
                <div className="text-[10px] text-secondary/60 uppercase tracking-[0.15em] font-medium">
                  {formatLabel(key)}
                </div>
                <FieldValue fieldKey={key} value={value} />
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default ProductView;
