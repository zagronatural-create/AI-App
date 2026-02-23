from pydantic import BaseModel


class RecallSimulationRequest(BaseModel):
    batch_code: str


class RecallSimulationResponse(BaseModel):
    batch_code: str
    impacted_customers_count: int
    impacted_qty: float
    suppliers_count: int
    finished_lots_count: int
    customers: list[dict]
