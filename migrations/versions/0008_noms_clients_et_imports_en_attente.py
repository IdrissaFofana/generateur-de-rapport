"""Autres noms des clients (reconnaissance à l'import) et imports en attente de client

Révision : 0008
Précédente : 0007
Créée le : 2026-09-30 14:03:36.134134
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import postgresql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('imports_en_attente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fichier', sa.String(length=500), nullable=False),
    sa.Column('nom_fichier', sa.String(length=300), nullable=False),
    sa.Column('extension', sa.String(length=10), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('texte', sa.Text(), nullable=False),
    sa.Column('nom_detecte', sa.String(length=200), nullable=True),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('empreinte')
    )
    op.add_column('clients', sa.Column('autres_noms', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade():
    op.drop_column('clients', 'autres_noms')
    op.drop_table('imports_en_attente')
