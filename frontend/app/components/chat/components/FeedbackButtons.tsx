"use client";

import { Message } from "@/app/types/chat";
import CopyToClipboardButton from "@/app/components/navigation/CopyButton";

interface FeedbackButtonsProps {
  conversationID: string;
  queryID: string;
  messages: Message[];
  query_start: Date;
  query_end: Date | null;
  feedback: number | null;
  updateFeedback: (
    conversationId: string,
    queryId: string,
    feedback: number
  ) => void;
}

const FeedbackButtons: React.FC<FeedbackButtonsProps> = ({
  conversationID,
  queryID,
  messages,
  query_start,
  query_end,
  feedback,
  updateFeedback,
}) => {
  return (
    <div className="w-full flex justify-end items-center gap-2">
      <p className="text-sm text-secondary">
        Finished in{" "}
        {query_end
          ? query_end.getTime() - query_start.getTime() > 60000
            ? `${Math.round(
                (query_end.getTime() - query_start.getTime()) / 60000
              )}m`
            : `${Math.round(
                (query_end.getTime() - query_start.getTime()) / 1000
              )}s`
          : "0s"}
      </p>
      <CopyToClipboardButton copyText={""} />
    </div>
  );
};

export default FeedbackButtons;
