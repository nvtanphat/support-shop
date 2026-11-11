export type Role = 'customer' | 'assistant' | 'staff' | 'system';

export interface Citation {
  clause_id: string;
  title: string;
  text?: string;
  effective_from?: string;
}

export interface Message {
  id: string;
  seq: number;
  role: Role;
  content: string;
  citations: string[];
  author_staff_id?: string | null;
  created_at?: string;
}

export interface PendingAction {
  id: string;
  conversation_id: string;
  type: 'cancel_order' | 'return';
  payload: Record<string, any>;
  payload_hash: string;
  preview: {
    title: string;
    description: string;
    order_code: string;
    breakdown?: Record<string, any>;
    estimated_refund_vnd?: number;
    requires_evidence?: boolean;
    requires_approval?: boolean;
    evidence_types?: string[];
  };
  status: 'proposed' | 'confirmed' | 'cancelled' | 'expired' | 'executed' | 'rejected';
  presented_at: string;
  expires_at: string;
  result?: Record<string, any>;
}

export interface OrderItem {
  id: string;
  sku: string;
  product_name?: string;
  qty: number;
  unit_price: number;
  allocated_discount: number;
  returned_qty: number;
}

export interface Order {
  id: string;
  code: string;
  status: string;
  payment_method: string;
  payment_status: string;
  subtotal: number;
  discount_total: number;
  shipping_fee: number;
  total: number;
  placed_at: string;
  delivered_at?: string | null;
  items: OrderItem[];
}

export interface ApprovalRequest {
  id: string;
  subject_type: string;
  subject_id: string;
  gate: string;
  required_role: string;
  status: 'pending' | 'approved' | 'rejected';
  requested_at: string;
  decided_by?: string | null;
  decided_at?: string | null;
  note?: string | null;
}

export interface Ticket {
  id: string;
  code: string;
  conversation_id: string;
  status: 'open' | 'in_progress' | 'resolved' | 'closed';
  priority: 'normal' | 'high' | 'urgent';
  reason_code: string;
  summary: string;
  assigned_to?: string | null;
  created_at: string;
}

export interface SSEEvent {
  event: string;
  data: any;
  id?: string;
}
