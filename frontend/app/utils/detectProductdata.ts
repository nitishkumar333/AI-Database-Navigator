import { ProductPayload } from "@/app/types/displays";

// ---------------------------------------------------------------------------
// Column‑name patterns (case‑insensitive). Each maps a ProductPayload field
// to an array of regex patterns that could match real‑world column names.
// ---------------------------------------------------------------------------

const IMAGE_COL_PATTERNS =
  /image|img|photo|thumbnail|picture|poster|avatar|logo|banner|cover|icon|media/i;

const FIELD_PATTERNS: Record<string, RegExp> = {
  name: /^(product[\s]?)?name$|^title$|^product[\s]?title$|^item[_\s]?name$/i,
  price:
    /price|cost|amount|unit[\s]?price|msrp|retail[\s]?price|selling[_\s]?price|mrp/i,
  description:
    /desc(ription)?|detail(s)?|summary|about|info(rmation)?|overview/i,
  brand: /brand|manufacturer|maker|vendor|company/i,
  category: /category|cat|type|class|group|department|genre/i,
  subcategory: /sub[\s]?category|sub[\s]?type|sub[_\s]?class/i,
  rating:
    /rating|score|stars|review[\s]?score|avg[\s]?rating|average[_\s]?rating/i,
  id: /^id$|product[\s]?id|item[\s]?id|sku|asin|upc|ean/i,
  collection: /collection|line|series/i,
  tags: /tags?|labels?|keywords?/i,
  url: /^url$|^link$|product[\s]?url|product[\s]?link|page[_\s]?url/i,
  reviews: /reviews?|review[\s]?count|num[\s]?reviews/i,
};

// ---------------------------------------------------------------------------
// Image‑URL value heuristics
// ---------------------------------------------------------------------------

const IMAGE_EXTENSIONS = /\.(jpe?g|png|gif|webp|svg|avif|bmp|tiff?|ico)(\?|#|$)/i;

const IMAGE_CDN_PATTERNS =
  /cloudinary|imgix|unsplash|pexels|cloudfront|amazonaws\.com\/.*\.(jpe?g|png|gif|webp)|googleusercontent|shopify|wixstatic|squarespace|imgur|flickr|pinimg|fbcdn/i;

/**
 * Check whether a string value looks like an image URL.
 */
function looksLikeImageUrl(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://"))
    return false;
  if (IMAGE_EXTENSIONS.test(trimmed)) return true;
  if (IMAGE_CDN_PATTERNS.test(trimmed)) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface DetectionResult {
  isProduct: boolean;
  imageField: string | null;
  /** Maps ProductPayload field → raw column name */
  fieldMapping: Record<string, string>;
}

/**
 * Analyse raw query result rows to decide whether the data should render
 * as a Product catalogue.
 *
 * Criteria (both must be true):
 *   1. At least one column contains image URLs
 *   2. At least one "product‑identifying" column exists (name/title OR price)
 */
export function detectProductData(
  rows: Record<string, unknown>[],
  columns?: string[]
): DetectionResult {
  const empty: DetectionResult = {
    isProduct: false,
    imageField: null,
    fieldMapping: {},
  };

  if (!rows || rows.length === 0) return empty;

  // Derive column list from the first row if not supplied.
  const cols = columns && columns.length > 0 ? columns : Object.keys(rows[0]);
  if (cols.length === 0) return empty;

  // --- Step 1: Detect image column ----------------------------------------

  let imageField: string | null = null;

  // 1a. Try column‑name heuristic first.
  for (const col of cols) {
    if (IMAGE_COL_PATTERNS.test(col)) {
      // Verify that at least one row has a URL‑like value in this column
      const hasUrl = rows
        .slice(0, 10)
        .some((r) => looksLikeImageUrl(r[col]));
      if (hasUrl) {
        imageField = col;
        break;
      }
    }
  }

  // 1b. Fallback: scan every column's values for image URLs.
  if (!imageField) {
    for (const col of cols) {
      const sampleRows = rows.slice(0, 10);
      const urlCount = sampleRows.filter((r) =>
        looksLikeImageUrl(r[col])
      ).length;
      // If ≥ 40 % of sampled rows have image URLs → treat as image column.
      if (urlCount >= Math.max(1, Math.ceil(sampleRows.length * 0.4))) {
        imageField = col;
        break;
      }
    }
  }

  if (!imageField) return empty;

  // --- Step 2: Build field mapping ----------------------------------------

  const fieldMapping: Record<string, string> = { image: imageField };

  for (const col of cols) {
    if (col === imageField) continue;
    for (const [field, pattern] of Object.entries(FIELD_PATTERNS)) {
      if (fieldMapping[field]) continue; // already mapped
      if (pattern.test(col)) {
        fieldMapping[field] = col;
        break;
      }
    }
  }

  // --- Step 3: Must have at least name/title OR price ---------------------

  const hasProductIdentifier = Boolean(
    fieldMapping.name || fieldMapping.price
  );

  if (!hasProductIdentifier) return empty;

  return { isProduct: true, imageField, fieldMapping };
}

/**
 * Convert raw row objects into ProductPayload[] using the detected mapping.
 */
export function mapRowsToProducts(
  rows: Record<string, unknown>[],
  fieldMapping: Record<string, string>
): ProductPayload[] {
  return rows.map((row) => {
    const product: ProductPayload = {};

    for (const [payloadField, colName] of Object.entries(fieldMapping)) {
      const rawValue = row[colName];
      if (rawValue === undefined || rawValue === null) continue;

      switch (payloadField) {
        case "price":
        case "rating": {
          const num = Number(rawValue);
          if (!isNaN(num)) {
            (product as Record<string, unknown>)[payloadField] = num;
          }
          break;
        }
        case "reviews": {
          const num = Number(rawValue);
          if (!isNaN(num)) {
            product.reviews = num;
          } else {
            product.reviews = String(rawValue)
              .split(",")
              .map((s) => s.trim());
          }
          break;
        }
        case "tags": {
          if (Array.isArray(rawValue)) {
            product.tags = rawValue.map(String);
          } else {
            const str = String(rawValue);
            // Handle JSON arrays, comma‑separated, or pipe‑separated
            try {
              const parsed = JSON.parse(str);
              if (Array.isArray(parsed)) {
                product.tags = parsed.map(String);
                break;
              }
            } catch {
              /* not JSON */
            }
            product.tags = str
              .split(/[,|;]/)
              .map((s) => s.trim())
              .filter(Boolean);
          }
          break;
        }
        default:
          (product as Record<string, unknown>)[payloadField] = String(
            rawValue
          );
      }
    }

    return product;
  });
}