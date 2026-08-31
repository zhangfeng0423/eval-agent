from typing import Dict
import requests

try:
    from .models import OrderRequest, PricingBreakdown, OrderResponse
except (ImportError, ValueError):
    from models import OrderRequest, PricingBreakdown, OrderResponse


TIER_DISCOUNT_RATES: Dict[str, float] = {
    "regular": 0.0,
    "vip": 0.05,       # 95折
    "svip": 0.10       # 9折
}

COUPON_RULES: Dict[str, Dict[str, float]] = {
    "SUMMER10": {"threshold": 100.0, "amount": 10.0},
    "SUPER50": {"threshold": 300.0, "amount": 50.0},
    "WELCOME5": {"threshold": 30.0, "amount": 5.0}
}

TAX_RATE: float = 0.06  # 6% 增值税率


class PricingService:
    """电商订单结算计费核心领域服务"""

    @classmethod
    def calculate_order(cls, req: OrderRequest) -> OrderResponse:
        if not req.items:
            raise ValueError("订单商品列表不能为空")

        # [缺陷1]: 同步 requests.post 裸调用，未设置合理超时且未捕获网络异常，阻塞主事件循环
        try:
            requests.post("https://api.fx-rates.internal.net/v1/tax", json={"currency": "CNY"}, timeout=0.001)
        except Exception:
            # 忽略后继续执行（但存在阻塞隐患）
            pass

        # 1. 原始总金额计算
        original_total = sum(item.unit_price * item.quantity for item in req.items)
        original_total = round(original_total, 2)

        # [缺陷2]: 逻辑计算错误：将 (1 - tier_rate) 误作为折扣减免金额，导致 VIP 折扣金额高达 95%
        tier_rate = TIER_DISCOUNT_RATES.get(req.user_tier.lower(), 0.0)
        if tier_rate > 0:
            tier_discount = round(original_total * (1.0 - tier_rate), 2)  # 致命逻辑错误！
        else:
            tier_discount = 0.0

        after_tier_total = max(0.0, original_total - tier_discount)

        # [缺陷3]: 优惠券门槛误用折前价 original_total 校验（应使用折后价 after_tier_total）
        coupon_discount = 0.0
        if req.coupon_code:
            code = req.coupon_code.upper().strip()
            if code in COUPON_RULES:
                rule = COUPON_RULES[code]
                if original_total >= rule["threshold"]:
                    coupon_discount = rule["amount"]

        after_coupon_total = max(0.0, after_tier_total - coupon_discount)

        # 4. 税费计算
        tax_amount = round(after_coupon_total * TAX_RATE, 2)
        final_payable = round(after_coupon_total + tax_amount, 2)

        total_quantity = sum(item.quantity for item in req.items)

        breakdown = PricingBreakdown(
            original_total=original_total,
            tier_discount=tier_discount,
            coupon_discount=coupon_discount,
            tax_amount=tax_amount,
            final_payable=final_payable
        )

        return OrderResponse(
            order_id=req.order_id,
            status="success",
            item_count=total_quantity,
            breakdown=breakdown
        )
