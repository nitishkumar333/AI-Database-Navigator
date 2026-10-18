"use client";

import React, { useContext } from "react";

import { QueryContext } from "../contexts/QueryContext";
import { AuthContext } from "../contexts/AuthContext";

import { MdChatBubbleOutline } from "react-icons/md";
import { FaCircle } from "react-icons/fa6";
import { MdOutlineSettingsInputComponent } from "react-icons/md";
import { HiOutlineBookOpen } from "react-icons/hi2";
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
  useSidebar,
} from "@/components/ui/sidebar";

import { Separator } from "@/components/ui/separator";

import { RouterContext } from "../contexts/RouterContext";
import { CollectionContext } from "../contexts/CollectionContext";
import { ConversationContext } from "../contexts/ConversationContext";

import ThemeToggle from "../shared/ThemeToggle";

const SidebarComponent: React.FC = () => {
  const { backendOnline } = useContext(QueryContext);
  const { changePage, currentPage } = useContext(RouterContext);
  const { connections, connectionsLoaded } = useContext(CollectionContext);
  const { startNewConversation, conversations, currentConversation } =
    useContext(ConversationContext);
  const openConversation = conversations.find(
    (c) => c.id === currentConversation
  );
  // Unloaded conversations have messages on the backend.
  const openConversationEmpty =
    !!openConversation &&
    openConversation.loaded &&
    Object.keys(openConversation.queries).length === 0;
  const { isAuthenticated, user, logout, onboardingStatus } =
    useContext(AuthContext);
  const { setOpenMobile } = useSidebar();

  const items: {
    title: string;
    active: boolean;
    icon: React.ReactNode;
    onClick: () => void;
  }[] = [
    {
      title: "New Chat",
      // Only highlighted while the open conversation has no messages yet.
      active: currentPage === "chat" && openConversationEmpty,
      icon: <MdChatBubbleOutline />,
      onClick: () => {
        setOpenMobile(false);
        // Without a database connection there is nothing to chat with,
        // so just open the chat page.
        if (connectionsLoaded && connections.length === 0) {
          changePage("chat", {}, true);
          return;
        }
        startNewConversation(true);
      },
    },
    {
      title: "Knowledge Base",
      active: currentPage === "knowledge",
      icon: <HiOutlineBookOpen />,
      onClick: () => {
        changePage("knowledge", {}, true);
        setOpenMobile(false);
      },
    },
    {
      title: "Database Connections",
      active: currentPage === "settings",
      icon: <MdOutlineSettingsInputComponent />,
      onClick: () => {
        changePage("settings", {}, true);
        setOpenMobile(false);
      },
    },
  ];

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
              className="w-5 h-5 dark:invert-0 invert transition-all"
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
                    variant={item.active ? "active" : "default"}
                    onClick={item.onClick}
                  >
                    <p className="flex items-center gap-2">
                      {item.icon}
                      <span>{item.title}</span>
                    </p>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <Separator />
        <HomeSubMenu />
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
                  <div className="flex items-center gap-1.5">
                    <p className="text-xs text-primary font-medium truncate">
                      {user?.is_guest || user?.username?.startsWith("guest_")
                        ? "Guest User"
                        : user?.username || "User"}
                    </p>
                    {(user?.is_guest || user?.username?.startsWith("guest_")) && (
                      <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-accent/20 text-accent font-semibold flex-shrink-0">
                        Demo
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {user?.email || ""}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-0.5 flex-shrink-0">
                <ThemeToggle variant="icon" size="sm" />
                <button
                  onClick={logout}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
                  title="Logout"
                >
                  <IoLogOutOutline size={16} />
                </button>
              </div>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
};

export default SidebarComponent;
