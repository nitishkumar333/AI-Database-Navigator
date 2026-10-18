import { ProductPayload } from "@/app/types/displays";

export type Message = {
  type: "result" | "text" | "User" | "suggestion";
  conversation_id: string;
  id: string;
  query_id: string;
  payload: ResultPayload | ResponsePayload | SuggestionPayload;
};

export type SuggestionPayload = {
  error: string;
  suggestions: string[];
};

export type ResponsePayload = {
  type: "response";
  objects: TextPayload[];
};

export type ResultPayload = {
  // "text" is the user's own question.
  type: "text" | "product" | "table";
  code: CodePayload;
  objects: string[] | ProductPayload[] | Record<string, unknown>[];
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
