from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class OrderItem(BaseModel):
    item_id: str = Field(..., min_length=1, description="商品唯一ID")
    name: str = Field(..., min_length=1, description="商品名称")
    unit_price: float = Field(..., gt=0, description="商品单价(必须大于0)")
    quantity: int = Field(..., gt=0, description="购买数量(必须大于0)")
    category: str = Field(default="general", description="商品分类")


class OrderRequest(BaseModel):
    order_id: str = Field(..., min_length=1, description="订单编号")
    items: List[OrderItem] = Field(..., min_length=1, description="订单商品列表")
    coupon_code: Optional[str] = Field(default=None, description="优惠券编码")
    user_tier: str = Field(default="regular", description="用户会员等级: regular, vip, svip")


class PricingBreakdown(BaseModel):
    original_total: float
    tier_discount: float
    coupon_discount: float
    tax_amount: float
    final_payable: float


class OrderResponse(BaseModel):
    order_id: str
    status: str = "success"
    item_count: int
    breakdown: PricingBreakdown
