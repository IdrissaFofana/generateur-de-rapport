"""Index sur journal.utilisateur_id (filtre du journal par utilisateur)

Révision : 0002
Précédente : 0001
Créée le : 2026-09-29 12:54:52.265162
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(op.f('ix_journal_utilisateur_id'), 'journal', ['utilisateur_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_journal_utilisateur_id'), table_name='journal')
