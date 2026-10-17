import { Query } from "@/app/types/chat";
import { v4 as uuidv4 } from "uuid";

export type Conversation = {
  id: string;
  name: string;
  queries: { [key: string]: Query };
  current: string;
  timestamp: Date;
  initialized: boolean;
  error: boolean;
  // Messages are in `queries`. False for a conversation listed from the
  // backend until it is opened and its messages are fetched.
  loaded: boolean;
};

export const initialConversation: Conversation = {
  id: uuidv4(),
  name: "New Conversation",
  error: false,
  timestamp: new Date(),
  current: "",
  queries: {},
  initialized: false,
  loaded: true,
};
