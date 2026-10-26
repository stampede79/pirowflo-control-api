"""use boolean recovery concern

Revision ID: 92ccf0d46cdc
Revises: 90a2e9634aca
Create Date: 2026-10-26 09:54:25.232406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92ccf0d46cdc'
down_revision: Union[str, Sequence[str], None] = '90a2e9634aca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table(
        "workout_analyses",
    ) as batch_op:
        batch_op.alter_column(
            "recovery_concern",
            existing_type=sa.String(length=30),
            type_=sa.Boolean(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "workout_analyses",
    ) as batch_op:
        batch_op.alter_column(
            "recovery_concern",
            existing_type=sa.Boolean(),
            type_=sa.String(length=30),
            existing_nullable=True,
        )
    # ### end Alembic commands ###
