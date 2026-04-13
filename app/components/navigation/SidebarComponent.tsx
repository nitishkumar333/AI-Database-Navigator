"use client";

import React, { useContext, useEffect, useState } from "react";

import { QueryContext } from "../contexts/SocketContext";

import { MdChatBubbleOutline } from "react-icons/md";
import { GoDatabase } from "react-icons/go";
import { FaCircle } from "react-icons/fa6";
import { MdOutlineSettingsInputComponent } from "react-icons/md";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { IoIosWarning } from "react-icons/io";

import HomeSubMenu from "@/app/components/navigation/HomeSubMenu";
import DataSubMenu from "@/app/components/navigation/DataSubMenu";

import { public_path } from "@/app/components/host";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenuItem,
  SidebarMenu,
  SidebarMenuButton,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar";

import { Separator } from "@/components/ui/separator";

import SettingsSubMenu from "./SettingsSubMenu";
import { RouterContext } from "../contexts/RouterContext";
import { CollectionContext } from "../contexts/CollectionContext";
import { SessionContext } from "../contexts/SessionContext";

const SidebarComponent: React.FC = () => {
  const { backendOnline } = useContext(QueryContext);
  const { changePage, currentPage } = useContext(RouterContext);
  const { collections, loadingCollections } = useContext(CollectionContext);
  const { unsavedChanges } = useContext(SessionContext);

  const [items, setItems] = useState<
    {
      title: string;
      mode: string[];
      icon: React.ReactNode;
      warning?: boolean;
      loading?: boolean;
      onClick: () => void;
    }[]
  >([]);

  useEffect(() => {
    const _items = [
      {
        title: "Chat",
        mode: ["chat"],
        icon: <MdChatBubbleOutline />,
        onClick: () => changePage("chat", {}, true, unsavedChanges),
      },
      {
        title: "Data",
        mode: ["data", "collection"],
        icon:
          collections.length === 0 ? (
            <IoIosWarning className="text-warning" />
          ) : (
            <GoDatabase />
          ),
        warning: collections.length === 0,
        loading: loadingCollections,
        onClick: () => changePage("data", {}, true, unsavedChanges),
      },
      {
        title: "Knowledge Base",
        mode: ["knowledge"],
        icon: <HiOutlineBookOpen />,
        onClick: () => changePage("knowledge", {}, true, unsavedChanges),
      },
      {
        title: "Settings",
        mode: ["settings"],
        icon: <MdOutlineSettingsInputComponent />,
        onClick: () => changePage("settings", {}, true, unsavedChanges),
      },
    ];
    setItems(_items);
  }, [collections, unsavedChanges]);

  return (
    <Sidebar className="fade-in">
      <SidebarHeader>
        <div className={`flex items-center gap-2 w-full justify-between p-2`}>
          <div className="flex items-center gap-2">
            <img
              src={`${public_path}logo.svg`}
              alt="AI Data Analyst"
              className="w-5 h-5"
            />
            <p className="text-sm font-bold text-primary">AI Data Analyst</p>
          </div>
          <div className="flex items-center justify-center gap-1">
            {backendOnline ? (
              <FaCircle
                scale={0.2}
                className="text-lg pulsing_color w-5 h-5"
              />
            ) : (
              <FaCircle scale={0.2} className="text-lg pulsing w-5 h-5" />
            )}
            <div className="flex flex-col items-end">
              <p className="text-xs text-muted-foreground">
                {backendOnline ? "Online" : "Offline"}
              </p>
            </div>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    asChild
                    variant={
                      item.mode.includes(currentPage)
                        ? "active"
                        : item.warning
                          ? "warning"
                          : "default"
                    }
                    onClick={item.onClick}
                  >
                    <p className="flex items-center gap-2">
                      {item.loading ? (
                        <FaCircle
                          scale={0.2}
                          className="text-lg pulsing_color"
                        />
                      ) : item.warning ? (
                        <IoIosWarning className="text-warning" />
                      ) : (
                        item.icon
                      )}
                      <span>{item.title}</span>
                    </p>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <Separator />

        {currentPage === "chat" && <HomeSubMenu />}
        {(currentPage === "data" || currentPage === "collection") && (
          <DataSubMenu />
        )}
        {currentPage === "knowledge" && <SettingsSubMenu />}
        {currentPage === "settings" && <SettingsSubMenu />}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton className="w-full justify-start items-center cursor-default hover:bg-transparent">
              <GoDatabase />
              <span className="text-xs text-muted-foreground">
                NL → SQL Platform
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
};

export default SidebarComponent;
