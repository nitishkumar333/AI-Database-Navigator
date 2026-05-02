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
  DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu";

import { CollectionContext } from "../../contexts/CollectionContext";

const CollectionSelection: React.FC = () => {
  const { collections } = useContext(CollectionContext);

  if (collections.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size={"icon"}>
          <GoDatabase className="text-primary" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56">
        <DropdownMenuLabel className="text-secondary">
          Connected Databases
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {collections.map((col) => (
          <DropdownMenuCheckboxItem
            checked={true}
            className="flex items-center justify-start gap-4"
            key={col.name}
            onSelect={(event) => {
              event.preventDefault();
            }}
          >
            <p className="text-primary text-xs">{col.name}</p>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default CollectionSelection;
