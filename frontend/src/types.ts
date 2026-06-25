export interface User {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  guideline: string;
  owner_id: number;
  auto_annotate_threshold: number;
  created_at: string;
}

export interface ProjectStats {
  total_documents: number;
  confirmed_documents: number;
  total_spans: number;
  total_relations: number;
  unreviewed_model_spans: number;
  unreviewed_model_relations: number;
}

export interface EntityType {
  id: number;
  name: string;
  color: string;
  hotkey: string;
}

export interface RelationType {
  id: number;
  name: string;
  color: string;
}

export interface Span {
  id: number;
  entity_type_id: number;
  start_offset: number;
  end_offset: number;
  source: "human" | "model";
  confidence: number | null;
  reviewed: boolean;
}

export interface Relation {
  id: number;
  relation_type_id: number;
  from_span_id: number;
  to_span_id: number;
  source: "human" | "model";
  confidence: number | null;
  reviewed: boolean;
}

export interface DocumentDetail {
  id: number;
  text: string;
  meta: Record<string, unknown>;
  is_confirmed: boolean;
  spans: Span[];
  relations: Relation[];
  prev_id: number | null;
  next_id: number | null;
  position: number;
  total: number;
}

export interface DocumentSummary {
  id: number;
  snippet: string;
  is_confirmed: boolean;
  span_count: number;
  relation_count: number;
  has_unreviewed: boolean;
}

export interface DocumentPage {
  total: number;
  page: number;
  page_size: number;
  items: DocumentSummary[];
}

export interface Member {
  id: number;
  user_id: number;
  username: string;
  role: string;
}

export interface TypeProgress {
  id: number;
  name: string;
  count: number;
  threshold: number;
  eligible: boolean;
}

export interface Eligibility {
  task: string;
  eligible: boolean;
  threshold: number;
  types: TypeProgress[];
  reason: string;
}

export interface TrainingJob {
  id: number;
  project_id: number;
  task: string;
  status: string;
  progress: number;
  message: string;
  metrics: Record<string, unknown>;
  annotated_count: number;
  created_at: string;
  finished_at: string | null;
}

export interface KeywordRule {
  id: number;
  entity_type_id: number;
  keyword: string;
  case_sensitive: boolean;
  whole_word: boolean;
}

export interface RelationRule {
  id: number;
  relation_type_id: number;
  head_entity_type_id: number;
  tail_entity_type_id: number;
  description: string;
  embedding_model: string;
  threshold: number;
  max_distance: number;
  has_embedding: boolean;
}

export interface ImportResult {
  imported_documents: number;
  imported_spans: number;
  imported_relations: number;
  created_entity_types: string[];
  created_relation_types: string[];
  warnings: string[];
}
