"use client";

import React, { useContext } from "react";

import { ConversationContext } from "../contexts/ConversationContext";

import { FaPlus } from "react-icons/fa6";
import { GoTrash } from "react-icons/go";

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarGroupLabel,
  SidebarGroupAction,
  SidebarMenuAction,
} from "@/components/ui/sidebar";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { SlOptionsVertical } from "react-icons/sl";

const HomeSubMenu: React.FC = () => {
  const {
    startNewConversation,
    currentConversation,
    removeConversation,
    selectConversation,
    conversations,
    creatingNewConversation,
  } = useContext(ConversationContext);

  return (
    <SidebarGroup>
      <div className="flex items-center justify-between">
        <SidebarGroupLabel className="flex items-center">
          <p>Conversations</p>
        </SidebarGroupLabel>
        <SidebarGroupAction
          title="Add Conversation"
          onClick={() => startNewConversation()}
          disabled={creatingNewConversation}
        >
          <FaPlus /> <span className="sr-only">Add Conversation</span>
        </SidebarGroupAction>
      </div>
      <SidebarGroupContent>
        {conversations
          .sort(
            (a, b) =>
              new Date(b.timestamp).getTime() -
              new Date(a.timestamp).getTime()
          )
          .map((conv) => (
            <SidebarMenuItem className="list-none fade-in" key={conv.id}>
              <SidebarMenuButton
                variant={
                  currentConversation === conv.id ? "active" : "default"
                }
                onClick={() => selectConversation(conv.id)}
              >
                <p className="truncate max-w-[13rem]">{conv.name}</p>
              </SidebarMenuButton>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <SidebarMenuAction>
                    <SlOptionsVertical />
                  </SidebarMenuAction>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="right" align="start">
                  <DropdownMenuItem
                    onClick={() => removeConversation(conv.id)}
                  >
                    <GoTrash className="text-error" />
                    <span className="text-error">Delete</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </SidebarMenuItem>
          ))}
      </SidebarGroupContent>
    </SidebarGroup>
  );
};

export default HomeSubMenu;
