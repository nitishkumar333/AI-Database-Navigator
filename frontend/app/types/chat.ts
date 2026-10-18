import { ResultData } from "@/app/types/results";

export type Message = {
  type: "result" | "text" | "User" | "suggestion";
  conversation_id: string;
  id: string;
  query_id: string;
  payload: ResultPayload | UserPayload | ResponsePayload | SuggestionPayload;
};

export type SuggestionPayload = {
  error: string;
  suggestions: string[];
};

export type ResponsePayload = {
  type: "response";
  objects: TextPayload[];
};

// The user's own question.
export type UserPayload = {
  type: "text";
  objects: string[];
};

export type ResultPayload = {
  type: "result";
  code: CodePayload;
  result: ResultData;
};

export type CodePayload = {
  language: string;
  title: string;
  text: string;
};

export type TextPayload = {
  text: string;
};

export type Query = {
  id: string;
  query: string;
  messages: Message[];
  finished: boolean;
  index: number;
};

export type Conversation = {
  id: string;
  name: string;
  queries: { [key: string]: Query };
  current: string;
  timestamp: Date;
  // Messages are in `queries`. False for a conversation listed from the
  // backend until it is opened and its messages are fetched.
  loaded: boolean;
};
