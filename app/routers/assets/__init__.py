"""Asset management routers — stock, real estate, summary."""

from app.routers.assets.stock import router as stock_router
from app.routers.assets.realestate import router as realestate_router
from app.routers.assets.summary import router as summary_router

__all__ = ["stock_router", "realestate_router", "summary_router"]
