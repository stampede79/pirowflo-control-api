"""allow unknown sessions per week

Revision ID: 2d595c235f46
Revises: 92ccf0d46cdc
Create Date: 2026-10-26 10:10:30.390561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d595c235f46'
down_revision: Union[str, Sequence[str], None] = '92ccf0d46cdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table(
        "training_plans",
    ) as batch_op:
        batch_op.alter_column(
            "sessions_per_week",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "training_plans",
    ) as batch_op:
        batch_op.alter_column(
            "sessions_per_week",
            existing_type=sa.Integer(),
            nullable=False,
        )
