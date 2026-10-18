"use client";

import React from "react";
import CopyToClipboardButton from "@/app/components/navigation/CopyButton";

interface UserMessageDisplayProps {
  text: string;
  onClick: () => void;
  collapsed: boolean;
}

const UserMessageDisplay: React.FC<UserMessageDisplayProps> = ({
  text,
  onClick,
  collapsed,
}) => {
  return (
    <div
      className="flex flex-col rounded-lg transition-all duration-300 justify-start items-start cursor-pointer w-full"
      onClick={onClick}
    >
      <div className="w-full">
        <div className="flex font-heading flex-grow justify-start items-start chat-animation gap-4">
          {!collapsed ? (
            <div className="flex gap-3 items-center">
              <p className="text-primary text-3xl text-left flex-grow">
                {text}
              </p>
              <CopyToClipboardButton copyText={text} />
            </div>
          ) : (
            <p className="text-secondary hover:text-primary text-xl transition-all duration-300 text-left">
              {text}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserMessageDisplay;
