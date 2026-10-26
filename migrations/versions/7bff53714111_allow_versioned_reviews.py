"""allow versioned reviews

Revision ID: 7bff53714111
Revises: 95113fb1b442
Create Date: 2026-10-26 11:20:08.686780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bff53714111'
down_revision: Union[str, Sequence[str], None] = '95113fb1b442'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table(
        "monthly_reviews",
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_monthly_review_month",
            type_="unique",
        )

    with op.batch_alter_table(
        "weekly_reviews",
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_weekly_review_week",
            type_="unique",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "weekly_reviews",
    ) as batch_op:
        batch_op.create_unique_constraint(
            "uq_weekly_review_week",
            [
                "year",
                "iso_week",
            ],
        )

    with op.batch_alter_table(
        "monthly_reviews",
    ) as batch_op:
        batch_op.create_unique_constraint(
            "uq_monthly_review_month",
            [
                "year",
                "month",
            ],
        )
