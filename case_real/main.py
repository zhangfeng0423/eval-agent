from fastapi import FastAPI, HTTPException
try:
    from .models import OrderRequest, OrderResponse
    from .service import PricingService
except (ImportError, ValueError):
    from models import OrderRequest, OrderResponse
    from service import PricingService

app = FastAPI(
    title="Order Pricing Service",
    description="工业级电商订单结算与阶梯计费微服务",
    version="1.0.0"
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "order-pricing"}


@app.post("/api/v1/orders/calculate", response_model=OrderResponse)
async def calculate_order_pricing(req: OrderRequest):
    try:
        return PricingService.calculate_order(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"结算异常: {str(e)}")
