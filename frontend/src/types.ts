export interface User {
  id: number;
  name: string;
  email: string;
}

export interface GroupMember {
  id: number;
  user_id: number;
  name: string;
  email: string;
  joined_at: string;
  left_at: string | null;
  active: boolean;
}

export interface Group {
  id: number;
  name: string;
  usd_inr_rate: number;
  created_at: string;
  members: GroupMember[];
}

export interface ExpenseSplit {
  user_id: number;
  name: string;
  amount_inr: number;
  original_amount: number | null;
  share_count: number | null;
  percentage: number | null;
}

export interface Expense {
  id: number;
  group_id: number;
  description: string;
  amount: number;
  currency: string;
  paid_by_user_id: number | null;
  paid_by_name: string | null;
  split_type: string;
  expense_date: string;
  notes: string | null;
  usd_inr_rate_used: number | null;
  splits: ExpenseSplit[];
  import_session_id: number | null;
}

export interface Settlement {
  id: number;
  group_id: number;
  payer_id: number;
  payer_name: string;
  receiver_id: number;
  receiver_name: string;
  amount: number;
  currency: string;
  settlement_date: string;
  notes: string | null;
}

export interface BalanceMember {
  name: string;
  net: number;
}

export interface SettlementTransaction {
  from_id: number;
  from: string;
  to_id: number;
  to: string;
  amount: number;
}

export interface GroupBalances {
  members: Record<string, BalanceMember>;
  transactions: SettlementTransaction[];
}

export interface BreakdownRow {
  expense_id: number;
  date: string;
  description: string;
  currency: string;
  original_amount: number;
  amount_inr: number;
  paid_by_user_id: number | null;
  i_paid_inr: number;
  my_share_inr: number;
  net_effect: number;
  split_type: string;
}

export interface MemberBreakdown {
  user_id: number;
  net: number;
  breakdown: BreakdownRow[];
}

export interface Anomaly {
  type: string;
  severity: 'info' | 'warning' | 'error';
  raw: string;
  message: string;
  default_action: string;
  resolved_value?: string | Record<string, number>;
  partner_row?: number;
}

export interface ImportRow {
  id: number;
  row_number: number;
  raw_data: Record<string, string>;
  parsed_data: Record<string, unknown>;
  status: string;
  anomalies: Anomaly[];
  expense_id: number | null;
}

export interface ImportReport {
  total_rows: number;
  clean: number;
  auto_fixed: number;
  needs_review: number;
  rejected: number;
  approved: number;
  anomaly_counts: Record<string, number>;
}

export interface ImportSession {
  session_id: number;
  status: string;
  report: ImportReport;
  rows: ImportRow[];
}
