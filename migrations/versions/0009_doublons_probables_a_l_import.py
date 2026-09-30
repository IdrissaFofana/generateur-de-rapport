"""Imports en attente : motif « doublon probable » (intervention semblable déjà enregistrée)

Révision : 0009
Précédente : 0008
Créée le : 2026-09-30 14:20:56.926232
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('imports_en_attente', sa.Column('motif', sa.String(length=20), server_default='client', nullable=False))
    op.add_column('imports_en_attente', sa.Column('client_id', sa.Integer(), nullable=True))
    op.add_column('imports_en_attente', sa.Column('doublon_id', sa.Integer(), nullable=True))
    op.add_column('imports_en_attente', sa.Column('similarite', sa.Float(), nullable=True))
    op.create_foreign_key('imports_en_attente_doublon_id_fkey', 'imports_en_attente', 'interventions', ['doublon_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('imports_en_attente_client_id_fkey', 'imports_en_attente', 'clients', ['client_id'], ['id'], ondelete='CASCADE')


def downgrade():
    op.drop_constraint('imports_en_attente_client_id_fkey', 'imports_en_attente', type_='foreignkey')
    op.drop_constraint('imports_en_attente_doublon_id_fkey', 'imports_en_attente', type_='foreignkey')
    op.drop_column('imports_en_attente', 'similarite')
    op.drop_column('imports_en_attente', 'doublon_id')
    op.drop_column('imports_en_attente', 'client_id')
    op.drop_column('imports_en_attente', 'motif')
