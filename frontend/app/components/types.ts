import { CodePayload, Query } from "@/app/types/chat";
import { v4 as uuidv4 } from "uuid";

export type FeedbackMetadata = {
  total_feedback: number;
  feedback_by_value: {
    positive: number;
    negative: number;
    superpositive: number;
  };
};

export type Conversation = {
  id: string;
  name: string;
  queries: { [key: string]: Query };
  current: string;
  timestamp: Date;
  initialized: boolean;
  error: boolean;
};

export const initialConversation: Conversation = {
  id: uuidv4(),
  name: "New Conversation",
  error: false,
  timestamp: new Date(),
  current: "",
  queries: {},
  initialized: false,
};
