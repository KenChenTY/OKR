import { localizedRecord } from "./i18n";
export interface User {
  id: number;
  name: string;
  role: string;
  org_id: number;
  csrf: string;
}
export interface Cycle {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
}
export interface Catalog {
  cycles: Cycle[];
  org_units: { id: number; name: string; parent_id: number | null }[];
  users: { id: number; name: string; role: string }[];
}
export interface Milestone {
  id: number;
  name: string;
  weight: string;
  due_date: string;
  accepted_at: string | null;
}
export interface KR {
  id: number;
  name: string;
  value_type: string;
  direction: string;
  baseline: string;
  current_value: string;
  target: string;
  weight: string;
  unit: string;
  frequency: string;
  evidence_source?: string;
  confidence: number;
  progress: string;
  raw_progress: string;
  health: string;
  next_due: string;
  etag: string;
  milestones: Milestone[];
}
export interface Evidence {
  id: number;
  name: string;
  kind: string;
  status: string;
  previous_id: number | null;
  uploaded_at: string;
  size: number;
  url: string | null;
}
export interface Approval {
  id: number;
  stage: string;
  status: string;
  assignee_id: number;
  assignee_name: string;
  comment: string;
  revision: number;
  decided_at: string | null;
}
export interface Objective {
  id: number;
  code: string;
  title: string;
  description: string;
  owner_id: number;
  owner_name: string;
  org_id: number;
  org_name: string;
  cycle_id: number;
  theme: string;
  priority: string;
  level: string;
  visibility: "organization" | "restricted";
  start_date: string;
  end_date: string;
  status: string;
  parent_id: number | null;
  revision: number;
  etag: string;
  kr_count: number;
  progress: string | null;
  health_counts: Record<string, number>;
  key_results?: KR[];
  approvals?: Approval[];
  evidence?: Evidence[];
}
export const statusNames: Record<string, string> = localizedRecord({
  Draft: "草稿",
  Submitted: "审批中",
  Approved: "已批准",
  Active: "执行中",
  Completed: "已完成",
  Cancelled: "已取消",
  Archived: "已归档",
});
export const healthNames: Record<string, string> = localizedRecord({
  Green: "进展正常",
  Amber: "存在风险",
  Red: "偏离计划",
  Gray: "缺少更新",
});
