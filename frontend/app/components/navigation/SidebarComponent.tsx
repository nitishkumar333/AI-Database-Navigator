"use client";

import React, { useContext, useEffect, useState } from "react";

import { QueryContext } from "../contexts/SocketContext";
import { AuthContext } from "../contexts/AuthContext";

import { MdChatBubbleOutline } from "react-icons/md";
import { GoDatabase } from "react-icons/go";
import { FaCircle } from "react-icons/fa6";
import { MdOutlineSettingsInputComponent } from "react-icons/md";
import { HiOutlineBookOpen } from "react-icons/hi2";
import { IoIosWarning } from "react-icons/io";
import { IoLogOutOutline } from "react-icons/io5";

import HomeSubMenu from "@/app/components/navigation/HomeSubMenu";

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
  const { isAuthenticated, user, logout, onboardingStatus } =
    useContext(AuthContext);

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

  // Don't render sidebar if not authenticated or onboarding not complete
  if (
    !isAuthenticated ||
    !onboardingStatus ||
    !onboardingStatus.onboarding_complete
  ) {
    return null;
  }

  return (
    <Sidebar className="fade-in">
      <SidebarHeader>
        <div className={`flex items-center gap-2 w-full justify-between p-2`}>
          <div className="flex items-center gap-2">
            <img
              src={`${public_path}logo.svg`}
              alt="SQLNav"
              className="w-5 h-5"
            />
            <p className="text-sm font-bold text-primary">SQLNav</p>
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
        {currentPage === "knowledge" && <SettingsSubMenu />}
        {currentPage === "settings" && <SettingsSubMenu />}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <div className="flex items-center justify-between w-full px-2 py-1">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0">
                  <span className="text-xs text-accent font-bold uppercase">
                    {user?.username?.charAt(0) || "U"}
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-primary font-medium truncate">
                    {user?.username || "User"}
                  </p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {user?.email || ""}
                  </p>
                </div>
              </div>
              <button
                onClick={logout}
                className="p-2 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
                title="Logout"
              >
                <IoLogOutOutline size={16} />
              </button>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
};

export default SidebarComponent;
