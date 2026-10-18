"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { CardsView, ResultData, Row } from "@/app/types/results";
import { columnLabel, columnMap, formatValue } from "@/app/utils/formatValue";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import DisplayPagination from "../../components/DisplayPagination";
import ResultImage from "./ResultImage";
import ResultValue from "./ResultValue";

// Fields shown on a card; the details dialog shows every column.
const CARD_FIELDS = 3;

const cardTitle = (row: Row, view: CardsView, index: number): string =>
  view.title && row[view.title] !== null && row[view.title] !== undefined
    ? String(row[view.title])
    : `Record ${index + 1}`;

/** Records with an image, as cards; a card opens all of its columns. */
const ResultCards: React.FC<{ view: CardsView; result: ResultData }> = ({ view, result }) => {
  const columns = columnMap(result.columns);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  // Kept while the dialog closes so its content stays during the animation.
  const [shownIndex, setShownIndex] = useState(0);
  const shown = result.rows[shownIndex];

  const open = (index: number) => {
    setShownIndex(index);
    setOpenIndex(index);
  };

  return (
    <div className="w-full">
      <DisplayPagination itemsPerPage={3}>
        {result.rows.map((row, index) => (
          <motion.button
            type="button"
            key={index}
            onClick={() => open(index)}
            whileHover={{ y: -3 }}
            whileTap={{ scale: 0.98 }}
            className="group flex h-full w-full flex-row sm:flex-col items-center sm:items-stretch gap-3 overflow-hidden rounded-xl border border-secondary/10 bg-background_alt p-2 sm:p-3 text-left shadow-sm transition-shadow hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ResultImage
              key={String(row[view.image] ?? index)}
              src={row[view.image]}
              alt={cardTitle(row, view, index)}
              className="h-16 w-16 sm:h-36 sm:w-full flex-shrink-0 rounded-lg"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <h3 className="line-clamp-2 text-sm font-semibold leading-tight text-primary">
                {cardTitle(row, view, index)}
              </h3>
              {view.fields.slice(0, CARD_FIELDS).map((field) => (
                <p key={field} className="truncate text-xs text-secondary">
                  <span className="text-secondary/70">{columnLabel(field)}: </span>
                  <span className="text-primary tabular-nums">
                    {formatValue(row[field], columns[field]?.type)}
                  </span>
                </p>
              ))}
            </div>
          </motion.button>
        ))}
      </DisplayPagination>

      <Dialog open={openIndex !== null} onOpenChange={(o) => !o && setOpenIndex(null)}>
        <DialogContent
          aria-describedby={undefined}
          className="w-[95vw] max-w-3xl max-h-[90vh] overflow-y-auto bg-background_alt border-foreground_alt rounded-2xl p-0"
        >
          <DialogTitle className="sr-only">
            {shown ? cardTitle(shown, view, shownIndex) : "Details"}
          </DialogTitle>
          {shown && (
            <div className="flex flex-col md:flex-row">
              <ResultImage
                key={String(shown[view.image] ?? shownIndex)}
                src={shown[view.image]}
                alt={cardTitle(shown, view, shownIndex)}
                fit="contain"
                className="h-64 md:h-auto md:min-h-80 md:w-2/5 flex-shrink-0"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-4 p-6">
                <h2 className="text-xl font-semibold text-primary pr-6">
                  {cardTitle(shown, view, shownIndex)}
                </h2>
                <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {result.columns
                    .filter((c) => c.name !== view.title && c.name !== view.image)
                    .map((column) => (
                      <div key={column.name} className="min-w-0">
                        <dt className="text-xs uppercase tracking-wide text-secondary">
                          {columnLabel(column.name)}
                        </dt>
                        <dd className="text-sm text-primary break-words">
                          {column.role === "image" ? (
                            <ResultImage
                              src={shown[column.name]}
                              alt={column.name}
                              className="mt-1 h-20 w-20 rounded-md"
                            />
                          ) : (
                            <ResultValue value={shown[column.name]} column={column} />
                          )}
                        </dd>
                      </div>
                    ))}
                </dl>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ResultCards;
