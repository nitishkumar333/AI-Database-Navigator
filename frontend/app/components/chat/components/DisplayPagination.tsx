"use client";

import React, { useEffect, useRef, useState } from "react";
import { FaChevronLeft, FaChevronRight } from "react-icons/fa";
import { motion, AnimatePresence, Variants } from "framer-motion";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const containerVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.4, 0, 0.2, 1],
    },
  },
  exit: {
    opacity: 0,
    y: -10,
    transition: {
      duration: 0.2,
      ease: [0.4, 0, 1, 1],
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: (index: number) => ({
    opacity: 1,
    scale: 1,
    transition: {
      delay: 0.1 + index * 0.1,
      duration: 0.3,
      ease: [0.4, 0, 0.2, 1],
    },
  }),
};

interface DisplayPaginationProps {
  children: React.ReactNode;
  itemsPerPage?: number;
}

/** Pages its children as a responsive grid of at most 3 columns. */
const DisplayPagination: React.FC<DisplayPaginationProps> = ({
  children,
  itemsPerPage = 3,
}) => {
  const [currentPage, setCurrentPage] = useState(0);
  const [dynamicItemsPerPage, setDynamicItemsPerPage] = useState(itemsPerPage);
  const bubbleContainerRef = useRef<HTMLDivElement>(null);

  const childrenArray = React.Children.toArray(children);
  const totalItems = childrenArray.length;
  const totalPages = Math.ceil(totalItems / dynamicItemsPerPage);

  // Get current page items
  const startIndex = currentPage * dynamicItemsPerPage;
  const currentItems = childrenArray.slice(
    startIndex,
    startIndex + dynamicItemsPerPage
  );

  const goToPage = (pageIndex: number) => {
    if (pageIndex >= 0 && pageIndex < totalPages) {
      setCurrentPage(pageIndex);
    }
  };
  const goToPrevious = () => goToPage(currentPage - 1);
  const goToNext = () => goToPage(currentPage + 1);

  const handleItemsPerPageChange = (value: string) => {
    setDynamicItemsPerPage(parseInt(value, 10));
    setCurrentPage(0); // Reset to first page when items per page changes
  };

  // Auto-scroll active bubble into view
  useEffect(() => {
    if (bubbleContainerRef.current && totalPages > 1) {
      const container = bubbleContainerRef.current;
      const activeBubble = container.children[currentPage] as HTMLElement;

      // Scroll only the bubble strip: scrollIntoView would also scroll every
      // ancestor (even overflow-hidden ones), shifting the whole page sideways.
      if (activeBubble) {
        const bubbleRect = activeBubble.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        container.scrollBy({
          left:
            bubbleRect.left +
            bubbleRect.width / 2 -
            (containerRect.left + containerRect.width / 2),
          behavior: "smooth",
        });
      }
    }
  }, [currentPage, totalPages]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const step = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
      const next = currentPage + step;
      if (step && next >= 0 && next < totalPages) setCurrentPage(next);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentPage, totalPages]);

  if (totalItems === 0) return null;

  // One item is centred with a limited width; more go in 2 or 3 columns.
  const containerClass =
    dynamicItemsPerPage === 1
      ? "flex justify-center"
      : dynamicItemsPerPage === 2
        ? "grid grid-cols-1 md:grid-cols-2"
        : "grid grid-cols-1 md:grid-cols-3";
  const itemContainerClass =
    dynamicItemsPerPage === 1 ? "w-full max-w-sm h-full" : "w-full h-full";
  const gapClass = "gap-4";

  return (
    <div className="w-full flex flex-col justify-start items-start gap-4">
      <style jsx>{`
        .scrollbar-none::-webkit-scrollbar {
          display: none;
        }
      `}</style>
      {/* Main carousel container */}
      <div className="w-full">
        <div
          className="flex flex-col w-full justify-start items-start gap-2 rounded-lg"
        >
          {/* Carousel content with dynamic layout */}
          <AnimatePresence mode="wait">
            <motion.div
              key={currentPage}
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              className={`${containerClass} w-full h-full ${gapClass}`}
            >
              {currentItems.map((child, index) => (
                <motion.div
                  key={`${currentPage}-${index}`}
                  variants={itemVariants}
                  initial="hidden"
                  animate="visible"
                  custom={index}
                  className={itemContainerClass}
                >
                  {child}
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Items per page selector */}
      <div className="flex justify-between items-center w-full">
        <div className="flex items-center gap-2">
          <span className="text-sm text-secondary">Items per page:</span>
          <Select
            value={dynamicItemsPerPage.toString()}
            onValueChange={handleItemsPerPageChange}
          >
            <SelectTrigger className="w-24 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1</SelectItem>
              <SelectItem value="2">2</SelectItem>
              <SelectItem value="3">3</SelectItem>
              <SelectItem value="6">6</SelectItem>
              <SelectItem value="9">9</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Show pagination info */}
        <div className="text-sm text-secondary">
          {totalItems > 0 && (
            <span>
              {startIndex + 1}-
              {Math.min(startIndex + dynamicItemsPerPage, totalItems)} of{" "}
              {totalItems}
            </span>
          )}
        </div>
      </div>

      {/* Navigation controls */}
      {totalPages > 1 && (
        <motion.div
          className="flex justify-center items-center w-full gap-3"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.3 }}
        >
          {/* Previous arrow */}
          <motion.button
            onClick={goToPrevious}
            disabled={currentPage === 0}
            whileHover={currentPage === 0 ? {} : { scale: 1.1 }}
            whileTap={currentPage === 0 ? {} : { scale: 0.95 }}
            className={`p-1.5 rounded-full transition-all duration-200 ${
              currentPage === 0
                ? "opacity-30 cursor-not-allowed text-secondary"
                : "hover:bg-foreground_alt text-primary"
            }`}
          >
            <FaChevronLeft className="w-3 h-3" />
          </motion.button>

          {/* Page indicators (dots) */}
          <div
            ref={bubbleContainerRef}
            className="flex items-center gap-2 max-w-72 overflow-x-auto px-2 scrollbar-none"
            style={{
              scrollbarWidth: "none", // Firefox
              msOverflowStyle: "none", // IE/Edge
            }}
          >
            {Array.from({ length: totalPages }, (_, index) => (
              <motion.button
                key={index}
                onClick={() => goToPage(index)}
                whileHover={{ scale: 1.25 }}
                whileTap={{ scale: 0.9 }}
                className={`h-2 rounded-full transition-all duration-300 flex-shrink-0 ${
                  index === currentPage
                    ? "w-8 bg-primary shadow-md"
                    : "w-2 bg-secondary hover:bg-primary/70"
                }`}
                aria-label={`Go to page ${index + 1}`}
              />
            ))}
          </div>

          {/* Next arrow */}
          <motion.button
            onClick={goToNext}
            disabled={currentPage === totalPages - 1}
            whileHover={currentPage === totalPages - 1 ? {} : { scale: 1.1 }}
            whileTap={currentPage === totalPages - 1 ? {} : { scale: 0.95 }}
            className={`p-1.5 rounded-full transition-all duration-200 ${
              currentPage === totalPages - 1
                ? "opacity-30 cursor-not-allowed text-secondary"
                : "hover:bg-foreground_alt text-primary"
            }`}
          >
            <FaChevronRight className="w-3 h-3" />
          </motion.button>
        </motion.div>
      )}
    </div>
  );
};

export default DisplayPagination;
