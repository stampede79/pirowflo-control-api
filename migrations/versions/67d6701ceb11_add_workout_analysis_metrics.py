"""add workout analysis metrics

Revision ID: 67d6701ceb11
Revises: b511a53b970c
Create Date: 2026-11-02 09:49:06.683299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67d6701ceb11'
down_revision: Union[str, Sequence[str], None] = 'b511a53b970c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "workout_analyses",
        sa.Column(
            "metrics_json",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column(
        "workout_analyses",
        "metrics_json",
    )