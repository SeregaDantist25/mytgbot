"""repair orders + status history

Revision ID: 0001_repair_orders
Revises:
Create Date: 2026-08-13

Первая миграция под управлением Alembic. Добавляет только новые таблицы
заявок на ремонт (repair_orders) и историю их статусов
(order_status_history). Существующие таблицы (users, ships, documents и
т.д.) не трогаем — они исторически создавались через ORM create_all и
самодельный _ensure_column; их приведение под Alembic — отдельная задача.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_repair_orders"
down_revision = None
branch_labels = None
depends_on = None


def _existing(inspector):
    """Возвращает (множество таблиц, функция-проверка индекса)."""
    tables = set(inspector.get_table_names())

    def has_index(table, index_name):
        if table not in tables:
            return False
        return index_name in {ix["name"] for ix in inspector.get_indexes(table)}

    return tables, has_index


def upgrade() -> None:
    """Идемпотентно создаёт таблицы заявок.

    В этом проекте таблицы исторически создаются через
    Base.metadata.create_all() при старте бота (models.init_models),
    поэтому repair_orders / order_status_history могут уже
    существовать. Создаём только то, чего нет, чтобы
    upgrade не падал на "table already exists".
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables, has_index = _existing(inspector)

    if "repair_orders" not in tables:
        op.create_table(
            "repair_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("ship_id", sa.Integer(), sa.ForeignKey("ships.id"), nullable=False),
            sa.Column("work_type", sa.String()),
            sa.Column("status", sa.String(), nullable=False, server_default="new"),
            sa.Column("cost_kopecks", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.telegram_id")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if not has_index("repair_orders", "ix_repair_orders_ship_id"):
        op.create_index("ix_repair_orders_ship_id", "repair_orders", ["ship_id"])
    if not has_index("repair_orders", "ix_repair_orders_status"):
        op.create_index("ix_repair_orders_status", "repair_orders", ["status"])

    if "order_status_history" not in tables:
        op.create_table(
            "order_status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("repair_orders.id"), nullable=False),
            sa.Column("from_status", sa.String()),
            sa.Column("to_status", sa.String(), nullable=False),
            sa.Column("changed_by", sa.BigInteger()),
            sa.Column("changed_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if not has_index("order_status_history", "ix_order_status_history_order_id"):
        op.create_index(
            "ix_order_status_history_order_id", "order_status_history", ["order_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables, has_index = _existing(inspector)

    if has_index("order_status_history", "ix_order_status_history_order_id"):
        op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    if "order_status_history" in tables:
        op.drop_table("order_status_history")
    if has_index("repair_orders", "ix_repair_orders_status"):
        op.drop_index("ix_repair_orders_status", table_name="repair_orders")
    if has_index("repair_orders", "ix_repair_orders_ship_id"):
        op.drop_index("ix_repair_orders_ship_id", table_name="repair_orders")
    if "repair_orders" in tables:
        op.drop_table("repair_orders")
