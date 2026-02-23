from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplierDelivery(Base):
    __tablename__ = "supplier_deliveries"

    delivery_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=False
    )
    raw_material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_materials.raw_material_id"), nullable=False
    )
    supplier_lot_code: Mapped[str] = mapped_column(Text, nullable=False)
    received_qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    received_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class RawMaterial(Base):
    __tablename__ = "raw_materials"

    raw_material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    material_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)


class RawMaterialLot(Base):
    __tablename__ = "raw_material_lots"

    rm_lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_deliveries.delivery_id"), nullable=False
    )
    internal_lot_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class ProductionBatch(Base):
    __tablename__ = "production_batches"

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    product_sku: Mapped[str] = mapped_column(Text, nullable=False)
    produced_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class BatchMaterialMap(Base):
    __tablename__ = "batch_material_map"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id"), primary_key=True
    )
    rm_lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_material_lots.rm_lot_id"), primary_key=True
    )
    qty_used: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)


class FinishedProduct(Base):
    __tablename__ = "finished_products"

    finished_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id"), nullable=False
    )
    serial_lot_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mfg_date: Mapped[str] = mapped_column(Date, nullable=False)
    best_before: Mapped[str | None] = mapped_column(Date)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_type: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)


class DispatchRecord(Base):
    __tablename__ = "dispatch_records"

    dispatch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    finished_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finished_products.finished_id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    dispatch_qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    dispatched_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class ComplianceThreshold(Base):
    __tablename__ = "compliance_thresholds"

    threshold_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    parameter_code: Mapped[str] = mapped_column(Text, nullable=False)
    standard_name: Mapped[str] = mapped_column(Text, nullable=False)
    product_category: Mapped[str] = mapped_column(Text, nullable=False)
    limit_min: Mapped[float | None] = mapped_column(Numeric(14, 6))
    limit_max: Mapped[float | None] = mapped_column(Numeric(14, 6))
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[str] = mapped_column(Date, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(Date)


class QualityTestRecord(Base):
    __tablename__ = "quality_test_records"

    test_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parameter_code: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_name: Mapped[str] = mapped_column(Text, nullable=False)
    observed_value: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    tested_at: Mapped[str | None] = mapped_column(DateTime(timezone=True))


class CcpLog(Base):
    __tablename__ = "ccp_logs"

    ccp_log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id"), nullable=False
    )
    ccp_code: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    measured_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class AiRiskScore(Base):
    __tablename__ = "ai_risk_scores"

    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    risk_band: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[dict | None] = mapped_column(JSONB)
    scored_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecallCase(Base):
    __tablename__ = "recall_cases"

    recall_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    trigger_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id"), nullable=False
    )
    initiated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(Text, nullable=False, default="simulated")
    impacted_customers_count: Mapped[int] = mapped_column(nullable=False, default=0)
    impacted_qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)


class RecallMapping(Base):
    __tablename__ = "recall_mapping"

    recall_mapping_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    recall_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recall_cases.recall_id"), nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_batches.batch_id")
    )
    finished_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finished_products.finished_id")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id")
    )
    impact_type: Mapped[str] = mapped_column(Text, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict | None] = mapped_column(JSONB)
    prev_hash: Mapped[str | None] = mapped_column(Text)
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)


class KpiDaily(Base):
    __tablename__ = "kpi_daily"

    kpi_date: Mapped[str] = mapped_column(Date, primary_key=True)
    avg_recall_trace_time_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    supplier_risk_coverage_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    batch_compliance_auto_validation_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    avg_audit_report_gen_time_sec: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quality_deviation_rate: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
