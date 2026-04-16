"use client";

import React, { useContext } from "react";

import { GoDatabase } from "react-icons/go";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";

import { CollectionContext } from "../../contexts/CollectionContext";

interface CollectionSelectionProps {
  selectedConnectionId: number | null;
  onConnectionChange: (connectionId: number | null) => void;
}

const CollectionSelection: React.FC<CollectionSelectionProps> = ({
  selectedConnectionId,
  onConnectionChange,
}) => {
  const { connections } = useContext(CollectionContext);

  if (connections.length === 0) return null;

  const selectedName = selectedConnectionId
    ? connections.find((c) => c.id === selectedConnectionId)?.name || "DB"
    : null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={selectedName ? "default" : "icon"}
          className={`gap-1.5 ${selectedName ? "text-accent text-xs px-2" : ""}`}
        >
          <GoDatabase className={selectedName ? "text-accent" : "text-primary"} size={14} />
          {selectedName && (
            <span className="max-w-[120px] truncate">{selectedName}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56">
        <DropdownMenuLabel className="text-secondary">
          Select Connection
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={selectedConnectionId?.toString() || "auto"}
          onValueChange={(value) => {
            if (value === "auto") {
              onConnectionChange(null);
            } else {
              onConnectionChange(parseInt(value));
            }
          }}
        >
          <DropdownMenuRadioItem value="auto">
            <p className="text-primary text-xs">Auto (first available)</p>
          </DropdownMenuRadioItem>
          {connections.map((conn) => (
            <DropdownMenuRadioItem
              key={conn.id}
              value={conn.id.toString()}
            >
              <div className="flex flex-col">
                <p className="text-primary text-xs font-medium">{conn.name}</p>
                <p className="text-muted-foreground text-[10px]">
                  {conn.db_name}@{conn.host}
                </p>
              </div>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default CollectionSelection;
