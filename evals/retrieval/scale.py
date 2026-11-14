"""How policy retrieval behaves when the corpus grows from the 10 real clauses to a realistic library.

    uv run --extra rerank python -m evals.retrieval.scale [--sizes 10,50,100,150] [--json out.json]

The real 10 clauses stay in the corpus; the rest are synthetic, generated from templates on subjects the shop's
policy does not cover and that the question sets do not ask about (care instructions, account, privacy, invoices,
packaging, reviews, ...). They share the shop's vocabulary ("đơn hàng", "khách hàng", "sản phẩm"), so the labels of the
existing questions stay valid while the corpus gets crowded. Per size it reports:

- indexing cost (embedding the clauses) and the memory of the in-process index;
- time of the candidate stage (BM25 + vectors + fusion) and of the whole retrieval per question;
- whether the right clause is still among the candidates handed to the reranker;
- Recall and out-of-scope rejection with the threshold frozen on 10 clauses (what production has today) and with a
  threshold recalibrated on that size (what `evals.retrieval.calibrate` would give).

Template-generated clauses are more repetitive than a real policy library, which makes ranking harder, and they cover
subjects far from the questions, which makes it easier. Treat the numbers as a stress test, not a forecast.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from itertools import product
from pathlib import Path
from typing import Any

from shopagent.rag import retriever as retriever_module
from shopagent.rag.documents import validate_clauses
from shopagent.rag.indexer import build_corpus
from shopagent.rag.reranker import CrossEncoderReranker
from shopagent.rag.retriever import HybridCandidates, PolicyRetriever

from evals.retrieval.holdout import MODEL, calibrate, load, report, score_all

# base topic -> (subjects, attributes, sentence templates)
TOPICS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "CARE": (
        ["cotton", "lụa", "len", "da thật", "da tổng hợp", "denim", "nỉ"],
        ["giặt", "phơi", "ủi", "cất giữ", "xử lý vết bẩn"],
        ["Hướng dẫn {attr} sản phẩm chất liệu {subject}: {audience} nên {attr} ở nhiệt độ không quá {n} độ và tránh {m} phút tiếp xúc trực tiếp với ánh nắng. Nội dung này chỉ là khuyến nghị sử dụng trên {channel}.",
         "Lưu ý khi {attr} đồ {subject}: thực hiện theo nhãn trên sản phẩm, không dùng chất tẩy mạnh quá {n} phần trăm nồng độ, để khô tự nhiên khoảng {m} giờ."],
    ),
    "ACCOUNT": (
        ["mật khẩu", "địa chỉ email", "số điện thoại", "ảnh đại diện", "tên hiển thị", "địa chỉ giao nhận", "ngôn ngữ giao diện"],
        ["cách thay đổi", "điều kiện thay đổi", "thời gian áp dụng", "số lần được thay đổi", "thông báo sau khi thay đổi"],
        ["Thay đổi {subject} của tài khoản: {attr} được mô tả cho {audience} khi dùng {channel}; tối đa {n} lần mỗi {m} ngày.",
         "Về {subject} trong tài khoản, phần {attr}: hệ thống ghi nhận thay đổi ngay và gửi thông báo trong {m} phút."],
    ),
    "PRIVACY": (
        ["thông tin liên hệ", "lịch sử mua hàng", "địa chỉ giao hàng", "dữ liệu thiết bị", "ảnh tải lên", "nội dung trò chuyện"],
        ["mục đích sử dụng", "thời gian lưu trữ", "quyền truy cập", "quyền chỉnh sửa", "quyền xóa"],
        ["Quyền riêng tư với {subject}: về {attr}, dữ liệu của {audience} được lưu tối đa {n} tháng và chỉ dùng cho vận hành dịch vụ trên {channel}.",
         "Chính sách dữ liệu cho {subject} ({attr}): khách hàng có thể gửi yêu cầu, thời hạn phản hồi {m} ngày làm việc."],
    ),
    "INVOICE": (
        ["hóa đơn điện tử", "thông tin xuất hóa đơn", "mã số thuế", "hóa đơn công ty", "bản sao hóa đơn", "điều chỉnh hóa đơn"],
        ["thời điểm phát hành", "cách đăng ký", "điều kiện", "cách nhận", "thời hạn yêu cầu"],
        ["Về {subject}, mục {attr}: {audience} cung cấp thông tin trước {m} ngày kể từ khi đặt trên {channel}; hóa đơn gửi qua email trong {n} ngày.",
         "Xuất {subject}: {attr} áp dụng cho đơn đã hoàn tất, yêu cầu gửi trong vòng {m} ngày."],
    ),
    "PACKAGING": (
        ["hộp carton", "túi giấy", "băng keo", "túi bóng khí", "hộp quà", "nhãn dán"],
        ["tiêu chuẩn", "tái chế", "kích thước", "đóng gói nhiều sản phẩm", "ghi chú trên kiện"],
        ["Quy cách đóng gói với {subject}: về {attr}, kiện hàng giao cho {audience} được đóng gói theo tiêu chuẩn nội bộ {n}, kiểm tra {m} bước trước khi niêm phong.",
         "Đóng gói bằng {subject} ({attr}): ưu tiên vật liệu có thể tái chế, áp dụng cho đơn đặt trên {channel}."],
    ),
    "REVIEW": (
        ["nhận xét bằng văn bản", "ảnh đánh giá", "video đánh giá", "điểm sao", "câu trả lời của cửa hàng", "đánh giá ẩn danh"],
        ["quy định đăng", "điều kiện được đăng", "thời gian duyệt", "nội dung bị từ chối", "chỉnh sửa sau khi đăng"],
        ["Đánh giá sản phẩm, {subject}: {attr}; {audience} có thể đăng sau khi nhận hàng, tối đa {n} ảnh, duyệt trong {m} giờ.",
         "Với {subject}, mục {attr}: nội dung không phù hợp bị gỡ, thông báo gửi qua {channel}."],
    ),
    "COOKIE": (
        ["cookie cần thiết", "cookie phân tích", "cookie quảng cáo", "bộ nhớ trình duyệt", "mã theo dõi phiên"],
        ["mục đích", "thời hạn lưu", "cách tắt", "ảnh hưởng khi tắt", "cách xóa"],
        ["Cookie trên {channel}: {subject}, phần {attr}; thời hạn lưu {n} ngày, {audience} có thể thay đổi lựa chọn bất cứ lúc nào.",
         "Về {subject} ({attr}): giữ tối đa {n} ngày, kiểm tra lại sau {m} lần truy cập."],
    ),
    "NEWSLETTER": (
        ["bản tin tuần", "thông báo sản phẩm mới", "nhắc giỏ hàng", "thông báo trạng thái đơn", "thư cảm ơn", "khảo sát sau mua"],
        ["tần suất gửi", "cách đăng ký", "cách hủy", "kênh nhận", "nội dung"],
        ["Thông báo qua email, {subject}: {attr}; {audience} nhận tối đa {n} thư mỗi tháng và có thể hủy trong {m} giây.",
         "Với {subject}, mục {attr}: gửi qua {channel}, cập nhật lựa chọn có hiệu lực trong {m} ngày."],
    ),
    "SECURITY": (
        ["đăng nhập hai bước", "mã xác minh", "thiết bị tin cậy", "phiên đăng nhập", "cảnh báo đăng nhập lạ", "khóa tạm thời"],
        ["cách bật", "cách tắt", "thời hạn hiệu lực", "số lần thử", "xử lý khi mất thiết bị"],
        ["Bảo mật tài khoản, {subject}: {attr}; mã có hiệu lực {m} phút, tối đa {n} lần thử cho {audience} trên {channel}.",
         "Về {subject} ({attr}): sau {n} lần sai tài khoản bị khóa {m} phút."],
    ),
    "ACCESS": (
        ["cỡ chữ", "chế độ tối", "đọc màn hình", "phím tắt", "độ tương phản", "ngôn ngữ"],
        ["cách bật", "thiết bị hỗ trợ", "giới hạn", "góp ý", "cập nhật"],
        ["Hỗ trợ truy cập trên {channel}: {subject}, {attr}; {audience} có thể bật trong phần cài đặt, hỗ trợ {n} mức.",
         "Tính năng {subject} ({attr}): áp dụng cho mọi trang, phản hồi trong {m} ngày."],
    ),
    "FEEDBACK": (
        ["góp ý giao diện", "báo lỗi", "đề xuất tính năng", "khiếu nại thái độ phục vụ", "khen ngợi nhân viên", "khảo sát hài lòng"],
        ["cách gửi", "thời gian phản hồi", "thông tin cần kèm", "theo dõi xử lý", "ẩn danh"],
        ["Tiếp nhận {subject}: {attr}; {audience} gửi qua {channel}, phản hồi trong {m} ngày làm việc, mã theo dõi gồm {n} ký tự.",
         "Với {subject} ({attr}): ghi nhận và chuyển bộ phận phụ trách trong {m} giờ."],
    ),
    "CONDUCT": (
        ["ngôn ngữ trao đổi", "nội dung bình luận", "ảnh đại diện", "tên hiển thị", "tin nhắn hàng loạt", "nội dung tải lên"],
        ["quy tắc", "hành vi bị cấm", "mức xử lý", "khiếu nại", "thời hạn khóa"],
        ["Quy tắc ứng xử, {subject}: {attr}; {audience} vi phạm {n} lần sẽ bị hạn chế {m} ngày trên {channel}.",
         "Về {subject} ({attr}): cửa hàng có quyền gỡ nội dung vi phạm và thông báo cho chủ tài khoản."],
    ),
    "SUSTAIN": (
        ["túi tái sử dụng", "hộp tái chế", "thu hồi bao bì", "quyên góp quần áo", "giảm giấy in", "điểm thu gom"],
        ["chương trình", "điều kiện tham gia", "cách tham gia", "ghi nhận đóng góp", "thời gian"],
        ["Chương trình môi trường, {subject}: {attr}; {audience} tham gia qua {channel}, ghi nhận tối đa {n} lần mỗi năm.",
         "Hoạt động {subject} ({attr}): báo cáo kết quả sau {m} tháng."],
    ),
    "APPUSE": (
        ["tìm kiếm sản phẩm", "lọc theo danh mục", "danh sách yêu thích", "so sánh sản phẩm", "lưu giỏ hàng", "lịch sử xem"],
        ["cách dùng", "giới hạn số lượng", "đồng bộ", "xóa dữ liệu", "lỗi thường gặp"],
        ["Hướng dẫn dùng {channel}: {subject}, {attr}; {audience} lưu tối đa {n} mục, đồng bộ sau {m} giây.",
         "Về {subject} ({attr}): dữ liệu giữ trên thiết bị và tài khoản trong {m} ngày."],
    ),
    "NOTIFY": (
        ["thông báo đẩy", "tin nhắn trong ứng dụng", "email giao dịch", "âm báo", "huy hiệu số", "nhắc việc"],
        ["cách bật", "cách tắt", "khung giờ", "nhóm thông báo", "ưu tiên"],
        ["Cài đặt thông báo, {subject}: {attr}; {audience} chọn khung giờ, tối đa {n} thông báo mỗi ngày trên {channel}.",
         "Với {subject} ({attr}): thay đổi có hiệu lực sau {m} phút."],
    ),
    "SUPPORTHOURS": (
        ["trợ lý tự động", "nhân viên trực chat", "biểu mẫu liên hệ", "hộp thư hỗ trợ", "hàng đợi ưu tiên", "bản ghi hội thoại"],
        ["cách sử dụng", "thời gian phản hồi", "giới hạn", "lưu trữ", "đánh giá chất lượng"],
        ["Kênh hỗ trợ, {subject}: {attr}; {audience} nhận phản hồi trong {m} phút, bản ghi lưu {n} ngày trên {channel}.",
         "Về {subject} ({attr}): ghi nhận mã yêu cầu để tra cứu lại."],
    ),
}
AUDIENCES = ["khách hàng mới", "khách hàng thân thiết", "khách hàng thông thường", "người dùng ứng dụng"]
CHANNELS = ["ứng dụng di động", "website", "trang quản lý tài khoản", "email"]


def synthetic_clauses(total: int, seed: int = 11) -> list[dict[str, Any]]:
    """Template-generated clauses with unique ids; the id format allows 99 per topic, so topics are split into letters."""
    rng = random.Random(seed)
    clauses: list[dict[str, Any]] = []
    group_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for base, (subjects, attrs, templates) in TOPICS.items():
        combos = list(product(subjects, attrs, AUDIENCES, CHANNELS))
        rng.shuffle(combos)
        for number, (subject, attr, audience, channel) in enumerate(combos):
            group, within = divmod(number, 99)
            text = rng.choice(templates).format(subject=subject, attr=attr, audience=audience, channel=channel, n=rng.randint(2, 30), m=rng.randint(2, 60))
            clauses.append(
                {
                    "clause_id": f"POL-{base}{group_letters[group]}-{within + 1:02d}",
                    "topic": base.lower(),
                    "category_scope": ["all"],
                    "version": "2026-11-01",
                    "effective_from": "2026-11-01T00:00:00+07:00",
                    "effective_to": None,
                    "text": text,
                    "source": "synthetic",
                    "status": "active",
                }
            )
    rng.shuffle(clauses)
    if len(clauses) < total:
        raise SystemExit(f"templates give {len(clauses)} clauses, {total} requested")
    return clauses[:total]


class CachedEmbedder:
    """Embeds each distinct text once across sizes, and records how long the clauses took."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.name, self.cache, self.seconds = inner, inner.name, {}, 0.0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if missing:
            started = time.perf_counter()
            self.cache.update(zip(missing, self.inner.embed_documents(missing), strict=True))
            self.seconds += time.perf_counter() - started
        return [self.cache[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)


class TimedCandidates:
    """The production candidate stage with a stopwatch, remembering the first 10 candidates of every question."""

    def __init__(self) -> None:
        self.inner, self.seconds, self.last_ids = HybridCandidates(), [], []

    def candidates(self, snapshot: Any, chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        started = time.perf_counter()
        ranked = self.inner.candidates(snapshot, chunks, query)
        self.seconds.append(time.perf_counter() - started)
        self.last_ids = [c["clause_id"] for c in ranked[:10]]
        return ranked


def rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / 2**20, 1)
    except ImportError:
        return None


async def candidate_recall(retriever: PolicyRetriever, timed: TimedCandidates, items: list[dict[str, Any]]) -> float:
    """Share of answerable questions with at least one right clause among the candidates given to the reranker."""
    hits = 0
    answerable = [i for i in items if i["expected"]]
    for item in answerable:
        timed.last_ids = []
        await retriever.retrieve(item["q"], top_k=4)
        hits += bool(set(timed.last_ids) & set(item["expected"]))
    return round(hits / len(answerable), 3)


async def run(sizes: list[int]) -> list[dict[str, Any]]:
    real = build_corpus()
    pool = synthetic_clauses(max(max(sizes) - len(real), 0))
    embedder = CachedEmbedder(retriever_module.get_configured_embedder())
    retriever_module.get_configured_embedder = lambda: embedder  # type: ignore[assignment]
    reranker = CrossEncoderReranker(MODEL)
    calibration_items, holdout_items = load("policy_queries_independent.yaml"), load("policy_queries_holdout.yaml")
    frozen: float | None = None
    results = []
    for size in sizes:
        clauses = real + pool[: size - len(real)]
        validate_clauses(clauses)
        retriever_module.build_corpus = lambda clauses=clauses: clauses  # type: ignore[assignment]
        timed = TimedCandidates()
        retriever = PolicyRetriever(in_memory=True, reranker=reranker, min_rerank_score=None, candidates=timed)
        before = rss_mb()
        started = time.perf_counter()
        await retriever.retrieve("đổi ý trong bao lâu", top_k=4)  # builds the index (embeds new clauses once)
        build_s = time.perf_counter() - started
        rows_cal = await score_all(retriever, calibration_items)
        rows_hold = await score_all(retriever, holdout_items)
        if frozen is None:
            frozen = calibrate(rows_cal)
        recalibrated = calibrate(rows_cal)
        times = [t * 1000 for t in timed.seconds]
        results.append(
            {
                "clauses": size,
                "embedding_seconds_total_so_far": round(embedder.seconds, 1),
                "first_query_including_index_build_s": round(build_s, 1),
                "rss_mb_before_after": [before, rss_mb()],
                "candidate_stage_ms": {"median": round(statistics.median(times), 1), "p95": round(sorted(times)[int(len(times) * 0.95) - 1], 1), "max": round(max(times), 1)},
                "candidate_recall@10": await candidate_recall(retriever, timed, holdout_items),
                "frozen_threshold": {**report(rows_hold, frozen), "threshold_used": round(frozen, 3)},
                "recalibrated_threshold": {**report(rows_hold, recalibrated), "threshold_used": round(recalibrated, 3)},
            }
        )
        keep = ("clauses", "candidate_recall@10")
        print(json.dumps({k: results[-1][k] for k in keep}, ensure_ascii=False), flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="10,50,100,150")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    os.environ.setdefault("RETRIEVAL_RERANKER_ENABLED", "true")
    results = asyncio.run(run([int(s) for s in args.sizes.split(",")]))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
