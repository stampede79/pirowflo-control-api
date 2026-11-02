"""add athlete profile

Revision ID: 57a90f75414d
Revises: 67d6701ceb11
Create Date: 2026-11-02 22:17:18.056068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57a90f75414d'
down_revision: Union[str, Sequence[str], None] = '67d6701ceb11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "athlete_profiles",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "max_heart_rate",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "heart_rate_zone_method",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "zone_1_min_percent",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "zone_2_min_percent",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "zone_3_min_percent",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "zone_4_min_percent",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "zone_5_min_percent",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "weight_kg",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "resting_heart_rate",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table(
        "athlete_profiles"
    )
