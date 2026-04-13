"use client";

import React, { useContext, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CollectionContext } from "../components/contexts/CollectionContext";
import { RouterContext } from "../components/contexts/RouterContext";
import { GoDatabase, GoTable, GoArrowRight } from "react-icons/go";
import { FaSpinner } from "react-icons/fa";

export default function DataPage() {
  const { collections, loadingCollections, fetchCollections } =
    useContext(CollectionContext);
  const { changePage } = useContext(RouterContext);

  return (
    <div className="flex flex-col w-full h-screen overflow-y-auto p-2 lg:p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col gap-6 w-full max-w-4xl mx-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-primary">
              Database Explorer
            </h1>
            <p className="text-sm text-muted-foreground">
              Browse your connected databases and explore their schemas
            </p>
          </div>
          <button
            onClick={fetchCollections}
            className="text-xs text-accent hover:text-accent/80 transition-colors"
          >
            Refresh
          </button>
        </div>

        {/* Loading */}
        {loadingCollections ? (
          <div className="flex items-center justify-center p-16">
            <FaSpinner className="animate-spin text-accent" size={32} />
          </div>
        ) : collections.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 p-16 border border-dashed border-foreground rounded-xl">
            <GoDatabase size={48} className="text-muted-foreground" />
            <p className="text-muted-foreground">
              No database connections found
            </p>
            <button
              onClick={() => changePage("settings", {}, true)}
              className="text-accent hover:text-accent/80 text-sm underline"
            >
              Go to Settings to add a connection
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {collections.map((collection, index) => (
              <motion.div
                key={collection.name}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08, duration: 0.4 }}
                onClick={() =>
                  changePage(
                    "collection",
                    { collection: collection.name },
                    true
                  )
                }
                className="group cursor-pointer border border-foreground rounded-xl p-6 hover:border-accent/50 hover:bg-foreground/20 transition-all duration-300"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent/20 to-accent/5 flex items-center justify-center">
                      <GoDatabase className="text-accent" size={24} />
                    </div>
                    <div>
                      <p className="font-semibold text-primary text-base">
                        {collection.name.split(" (")[0]}
                      </p>
                      {collection.name.includes("(") && (
                        <p className="text-xs text-muted-foreground">
                          {collection.name.match(/\(([^)]+)\)/)?.[1]}
                        </p>
                      )}
                    </div>
                  </div>
                  <GoArrowRight
                    className="text-muted-foreground group-hover:text-accent transition-colors"
                    size={18}
                  />
                </div>

                <div className="mt-4 flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <GoTable size={14} className="text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      {collection.total} tables
                    </span>
                  </div>
                  <div
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      collection.processed
                        ? "bg-green-500/10 text-green-400"
                        : "bg-yellow-500/10 text-yellow-400"
                    }`}
                  >
                    {collection.processed ? "Connected" : "Pending"}
                  </div>
                </div>

                {/* Sample prompts */}
                {collection.prompts && collection.prompts.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {collection.prompts.slice(0, 2).map((prompt, i) => (
                      <span
                        key={i}
                        className="text-xs text-muted-foreground bg-foreground/50 px-2 py-1 rounded-md truncate max-w-[200px]"
                      >
                        {prompt}
                      </span>
                    ))}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
