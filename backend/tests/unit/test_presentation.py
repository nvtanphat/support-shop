"""Internal codes never reach the customer, while labels and real identifiers stay."""

from shopagent.agent.presentation import strip_internal_codes


def test_codes_after_their_label_are_dropped_and_lone_codes_translated() -> None:
    seen_live = (
        "- Trạng thái đơn hàng: Đã giao (`delivered`) vào ngày 29/10/2026.\n"
        "2. Sản phẩm Home_living #111 — *sản phẩm này thuộc danh mục giảm giá cuối mùa / final_sale*.\n"
        "Lý do: `defective`."
    )
    assert strip_internal_codes(seen_live) == (
        "- Trạng thái đơn hàng: Đã giao vào ngày 29/10/2026.\n"
        "2. Sản phẩm Home_living #111 — *sản phẩm này thuộc danh mục giảm giá cuối mùa*.\n"
        "Lý do: sản phẩm bị lỗi."
    )


def test_order_codes_citations_and_ordinary_words_are_untouched() -> None:
    text = "Đơn **SL-001500** theo [POL-RETURN-01]; bạn muốn hoàn tiền hay đổi hàng? Mã `SL-001500`."
    assert strip_internal_codes(text) == text


def test_a_citation_wrapped_in_backticks_is_shown_as_a_plain_citation() -> None:
    # Seen in the live UI: "theo chính sách đổi trả do đổi ý `[POL-RETURN-02]`" rendered the backticks around the chip.
    assert strip_internal_codes("Theo chính sách `[POL-RETURN-02]`, bạn có 7 ngày.") == "Theo chính sách [POL-RETURN-02], bạn có 7 ngày."
