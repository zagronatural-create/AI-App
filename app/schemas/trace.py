from pydantic import BaseModel


class SupplierOut(BaseModel):
    supplier_id: str
    name: str


class RawMaterialLotOut(BaseModel):
    rm_lot_id: str
    internal_lot_code: str


class CustomerOut(BaseModel):
    customer_id: str
    name: str
    customer_type: str


class FinishedOut(BaseModel):
    finished_id: str
    serial_lot_code: str


class TraceResponse(BaseModel):
    batch_code: str
    backward: dict
    forward: dict
