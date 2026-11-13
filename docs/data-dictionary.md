# Từ điển dữ liệu

Sinh tự động bởi `python -m shopagent.cli data-dictionary` từ các model SQLAlchemy.

## audit_log

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| actor_type | VARCHAR(32) | không null |
| actor_id | VARCHAR(64) | không null |
| action | VARCHAR(64) | không null |
| subject_type | VARCHAR(32) | không null |
| subject_id | VARCHAR(64) | không null |
| before_state | JSON |  |
| after_state | JSON |  |
| request_id | VARCHAR(64) |  |
| at | DATETIME | không null |

## conversations

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| customer_id | CHAR(32) |  |
| guest_token | VARCHAR(64) |  |
| mode | VARCHAR(32) | không null |
| summary | TEXT | không null |
| prompt_hash | VARCHAR(64) | không null |
| last_event_seq | INTEGER | không null |
| last_message_seq | INTEGER | không null |
| created_at | DATETIME | không null |
| updated_at | DATETIME | không null |

## customers

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| email | VARCHAR(255) | không null, duy nhất |
| phone | VARCHAR(32) | không null, duy nhất |
| full_name | VARCHAR(255) | không null |
| tier | VARCHAR(32) | không null |
| created_at | DATETIME | không null |
| updated_at | DATETIME | không null |
| version | INTEGER | không null |

## guest_verifications

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| guest_token | VARCHAR(64) | không null |
| order_id | CHAR(32) |  |
| phone_hash | VARCHAR(64) | không null |
| otp_hash | VARCHAR(64) | không null |
| attempts | INTEGER | không null |
| expires_at | DATETIME | không null |
| verified_at | DATETIME |  |
| grant_expires_at | DATETIME |  |
| created_at | DATETIME | không null |

## idempotency_keys

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| key | VARCHAR(128) | khóa chính |
| scope | VARCHAR(64) | không null |
| response_digest | JSON | không null |
| created_at | DATETIME | không null |

## outbox_events

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| type | VARCHAR(64) | không null |
| payload | JSON | không null |
| status | VARCHAR(32) | không null |
| attempts | INTEGER | không null |
| next_attempt_at | DATETIME | không null |
| idempotency_key | VARCHAR(128) | không null, duy nhất |
| created_at | DATETIME | không null |

## pending_actions

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| conversation_id | CHAR(32) | không null |
| customer_id | CHAR(32) | không null |
| type | VARCHAR(32) | không null |
| payload | JSON | không null |
| payload_hash | VARCHAR(64) | không null |
| preview | JSON | không null |
| status | VARCHAR(32) | không null |
| presented_at | DATETIME | không null |
| expires_at | DATETIME | không null |
| result | JSON | không null |

## policy_documents

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| title | VARCHAR(255) | không null |
| slug | VARCHAR(128) | không null, duy nhất |
| version | VARCHAR(32) | không null |
| effective_from | DATETIME | không null |
| effective_to | DATETIME |  |
| created_at | DATETIME | không null |

## products

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| name | VARCHAR(255) | không null |
| category | VARCHAR(64) | không null |
| return_flags | JSON | không null |
| created_at | DATETIME | không null |

## staff_users

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| email | VARCHAR(255) | không null, duy nhất |
| password_hash | VARCHAR(255) | không null |
| role | VARCHAR(32) | không null |
| full_name | VARCHAR(255) | không null |
| created_at | DATETIME | không null |

## approval_requests

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| subject_type | VARCHAR(32) | không null |
| subject_id | CHAR(32) | không null |
| gate | VARCHAR(32) | không null |
| required_role | VARCHAR(32) | không null |
| status | VARCHAR(32) | không null |
| requested_at | DATETIME | không null |
| decided_by | CHAR(32) | khóa ngoại staff_users.id |
| decided_at | DATETIME |  |
| note | TEXT |  |

## conversation_events

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| conversation_id | CHAR(32) | không null, khóa ngoại conversations.id |
| seq | INTEGER | không null |
| type | VARCHAR(64) | không null |
| payload | JSON | không null |
| created_at | DATETIME | không null |

## customer_credentials

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| customer_id | CHAR(32) | khóa chính, khóa ngoại customers.id |
| password_hash | VARCHAR(255) | không null |
| created_at | DATETIME | không null |

## messages

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| conversation_id | CHAR(32) | không null, khóa ngoại conversations.id |
| seq | INTEGER | không null |
| role | VARCHAR(16) | không null |
| content | TEXT | không null |
| citations | JSON | không null |
| author_staff_id | CHAR(32) |  |
| created_at | DATETIME | không null |

## orders

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| code | VARCHAR(32) | không null, duy nhất |
| customer_id | CHAR(32) | không null, khóa ngoại customers.id |
| status | VARCHAR(32) | không null |
| payment_method | VARCHAR(32) | không null |
| payment_status | VARCHAR(32) | không null |
| subtotal | BIGINT | không null |
| discount_total | BIGINT | không null |
| shipping_fee | BIGINT | không null |
| total | BIGINT | không null |
| paid_amount | BIGINT | không null |
| refunded_amount | BIGINT | không null |
| channel | VARCHAR(32) | không null |
| note | TEXT |  |
| policy_version | VARCHAR(32) | không null |
| placed_at | DATETIME | không null |
| delivered_at | DATETIME |  |
| created_at | DATETIME | không null |
| updated_at | DATETIME | không null |
| version | INTEGER | không null |

## policy_chunks

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| document_id | CHAR(32) | không null, khóa ngoại policy_documents.id |
| clause_id | VARCHAR(64) | không null |
| topic | VARCHAR(64) | không null |
| category_scope | JSON | không null |
| version | VARCHAR(32) | không null |
| effective_from | DATETIME | không null |
| effective_to | DATETIME |  |
| text | TEXT | không null |
| text_unaccent | TEXT | không null |
| embedding | JSON | không null |
| created_at | DATETIME | không null |

## product_variants

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| product_id | CHAR(32) | không null, khóa ngoại products.id |
| sku | VARCHAR(64) | không null, duy nhất |
| attributes | JSON | không null |
| price | BIGINT | không null |
| stock | INTEGER | không null |

## tickets

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| code | VARCHAR(32) | không null, duy nhất |
| conversation_id | CHAR(32) | không null |
| customer_id | CHAR(32) |  |
| reason_code | VARCHAR(32) | không null |
| priority | VARCHAR(16) | không null |
| status | VARCHAR(32) | không null |
| assignee | CHAR(32) | khóa ngoại staff_users.id |
| agent_summary | TEXT | không null |
| context | JSON | không null |
| created_at | DATETIME | không null |

## order_items

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| order_id | CHAR(32) | không null, khóa ngoại orders.id |
| variant_id | CHAR(32) | không null, khóa ngoại product_variants.id |
| qty | INTEGER | không null |
| unit_price | BIGINT | không null |
| allocated_discount | BIGINT | không null |
| returned_qty | INTEGER | không null |
| exchanged | BOOLEAN | không null |

## payments

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| order_id | CHAR(32) | không null, khóa ngoại orders.id |
| gateway | VARCHAR(32) | không null |
| gateway_txn_id | VARCHAR(128) | không null |
| amount | BIGINT | không null |
| status | VARCHAR(32) | không null |
| mode | VARCHAR(32) | không null |
| created_at | DATETIME | không null |

## return_requests

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| code | VARCHAR(32) | không null, duy nhất |
| order_id | CHAR(32) | không null, khóa ngoại orders.id |
| customer_id | CHAR(32) | không null, khóa ngoại customers.id |
| reason_code | VARCHAR(32) | không null |
| resolution | VARCHAR(16) | không null |
| status | VARCHAR(32) | không null |
| risk_flags | JSON | không null |
| policy_version | VARCHAR(32) | không null |
| decided_by | VARCHAR(64) |  |
| deadline_ship_back | DATETIME |  |
| created_at | DATETIME | không null |
| updated_at | DATETIME | không null |
| version | INTEGER | không null |

## shipments

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| order_id | CHAR(32) | không null, khóa ngoại orders.id |
| carrier | VARCHAR(64) | không null |
| tracking_code | VARCHAR(64) | không null, duy nhất |
| status | VARCHAR(32) | không null |
| direction | VARCHAR(16) | không null |
| created_at | DATETIME | không null |

## evidence_files

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| return_id | CHAR(32) | không null, khóa ngoại return_requests.id |
| kind | VARCHAR(32) | không null |
| path | VARCHAR(512) | không null |
| sha256 | VARCHAR(64) | không null |
| size | BIGINT | không null |
| uploaded_by | VARCHAR(64) | không null |
| created_at | DATETIME | không null |

## exchanges

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| return_id | CHAR(32) | không null, khóa ngoại return_requests.id |
| new_variant_id | CHAR(32) | không null, khóa ngoại product_variants.id |
| new_shipment_id | CHAR(32) | khóa ngoại shipments.id |
| status | VARCHAR(32) | không null |
| created_at | DATETIME | không null |

## refunds

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| code | VARCHAR(32) | không null, duy nhất |
| order_id | CHAR(32) | không null, khóa ngoại orders.id |
| return_id | CHAR(32) | khóa ngoại return_requests.id |
| amount | BIGINT | không null |
| breakdown | JSON | không null |
| method | VARCHAR(32) | không null |
| status | VARCHAR(32) | không null |
| gateway_txn_id | VARCHAR(128) |  |
| attempts | INTEGER | không null |
| created_at | DATETIME | không null |
| updated_at | DATETIME | không null |
| version | INTEGER | không null |

## return_items

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| return_id | CHAR(32) | không null, khóa ngoại return_requests.id |
| order_item_id | CHAR(32) | không null, khóa ngoại order_items.id |
| qty | INTEGER | không null |
| inspection_result | VARCHAR(32) | không null |

## shipment_events

| Cột | Kiểu | Ràng buộc |
|---|---|---|
| id | CHAR(32) | khóa chính |
| shipment_id | CHAR(32) | không null, khóa ngoại shipments.id |
| status | VARCHAR(32) | không null |
| location | VARCHAR(255) | không null |
| occurred_at | DATETIME | không null |
