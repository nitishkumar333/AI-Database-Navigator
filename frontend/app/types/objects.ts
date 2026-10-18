export type Connection = {
  id: number;
  name: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  created_at?: string;
};

export type KnowledgeBaseGroup = {
  id: number;
  connection_id: number;
  name: string;
  tables: string[];
  created_at: string;
};

export type TableInfo = {
  name: string;
  column_count: number;
};
