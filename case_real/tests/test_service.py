import sys
from pathlib import Path

# 确保父目录在 sys.path 中
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from models import OrderRequest, OrderItem
    from service import PricingService
except ImportError:
    from ..models import OrderRequest, OrderItem
    from ..service import PricingService

import unittest


class TestPricingService(unittest.TestCase):

    def test_regular_order_calculation(self):
        req = OrderRequest(
            order_id="ORD-001",
            items=[
                OrderItem(item_id="P101", name="机械键盘", unit_price=100.0, quantity=2),
                OrderItem(item_id="P102", name="鼠标垫", unit_price=20.0, quantity=1)
            ],
            user_tier="regular"
        )
        res = PricingService.calculate_order(req)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.item_count, 3)
        self.assertEqual(res.breakdown.original_total, 220.0)
        self.assertEqual(res.breakdown.tier_discount, 0.0)
        self.assertEqual(res.breakdown.coupon_discount, 0.0)
        self.assertEqual(res.breakdown.tax_amount, 13.20)
        self.assertEqual(res.breakdown.final_payable, 233.20)

    def test_vip_with_coupon_calculation(self):
        req = OrderRequest(
            order_id="ORD-002",
            items=[
                OrderItem(item_id="P201", name="降噪耳机", unit_price=350.0, quantity=1)
            ],
            user_tier="vip",
            coupon_code="SUMMER10"
        )
        res = PricingService.calculate_order(req)
        self.assertEqual(res.breakdown.original_total, 350.0)
        # 95折: 350 * 0.05 = 17.50
        self.assertEqual(res.breakdown.tier_discount, 17.50)
        # 350 - 17.5 = 332.50 >= 100 门槛, 抵扣 10
        self.assertEqual(res.breakdown.coupon_discount, 10.0)
        # after coupon = 322.50, tax = 322.50 * 0.06 = 19.35
        self.assertEqual(res.breakdown.tax_amount, 19.35)
        self.assertEqual(res.breakdown.final_payable, 341.85)

    def test_coupon_threshold_not_met(self):
        req = OrderRequest(
            order_id="ORD-003",
            items=[
                OrderItem(item_id="P301", name="USB线", unit_price=25.0, quantity=1)
            ],
            user_tier="regular",
            coupon_code="WELCOME5"  # 门槛30元，25元未达门槛
        )
        res = PricingService.calculate_order(req)
        self.assertEqual(res.breakdown.coupon_discount, 0.0)
        self.assertEqual(res.breakdown.tax_amount, 1.50)
        self.assertEqual(res.breakdown.final_payable, 26.50)


if __name__ == "__main__":
    unittest.main()
