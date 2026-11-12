"""Pydantic schemas for REST API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(description="Email đăng nhập của khách hàng.")
    password: str = Field(description="Mật khẩu.")


class StaffLoginRequest(BaseModel):
    email: str = Field(description="Email đăng nhập nhân viên.")
    password: str = Field(description="Mật khẩu nhân viên.")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    email: str


# -----------------------------------------------------------------------------
# Conversation & Messages
# -----------------------------------------------------------------------------
class CreateConversationRequest(BaseModel):
    channel: str = Field(default="web", description="Kênh tương tác: web, mobile.")


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000, description="Nội dung tin nhắn khách gửi.")
    idempotency_key: str | None = Field(default=None, description="Khóa chống trùng lặp theo lượt gửi của client.")


class MessageDto(BaseModel):
    id: str
    seq: int
    role: str
    content: str
    citations: list[str] = []
    created_at: str


class ConversationDto(BaseModel):
    id: str
    conversation_id: str | None = None
    customer_id: str | None = None
    guest_token: str | None = None
    channel: str = "web"
    mode: str = "ai"
    created_at: str
    messages: list[MessageDto] = []
    pending_actions: list[dict[str, Any]] = []


# -----------------------------------------------------------------------------
# Actions & Confirmations
# -----------------------------------------------------------------------------
class ConfirmActionRequest(BaseModel):
    preview_hash: str = Field(description="Mã băm SHA-256 của bản xem trước được xác nhận.")


class CancelActionRequest(BaseModel):
    reason: str = Field(default="Khách hàng hủy yêu cầu", description="Lý do hủy đề xuất.")


# -----------------------------------------------------------------------------
# Guest Verifications
# -----------------------------------------------------------------------------
class GuestVerificationRequest(BaseModel):
    order_code: str = Field(description="Mã đơn hàng cần xác minh.")
    phone: str = Field(description="Số điện thoại nhận hàng.")


class GuestVerifyOtpRequest(BaseModel):
    otp: str = Field(min_length=6, max_length=6, description="Mã OTP 6 chữ số gửi qua SMS.")


# -----------------------------------------------------------------------------
# Staff Workflow
# -----------------------------------------------------------------------------
class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(description="approve hoặc reject.")
    note: str = Field(min_length=3, description="Ghi chú bắt buộc giải thích lý do.")


class StaffHandoffMessageRequest(BaseModel):
    content: str = Field(min_length=1, description="Tin nhắn của nhân viên gửi tới khách.")
