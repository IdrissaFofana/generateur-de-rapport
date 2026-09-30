"""Contrats et licences, alertes, envois périodiques (résumé hebdomadaire)

Révision : 0004
Précédente : 0003
Créée le : 2026-09-29 15:52:38.546874
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('envois',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('periode', sa.String(length=20), nullable=False),
    sa.Column('envoye_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('type', 'periode')
    )
    op.create_table('alertes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cle', sa.String(length=200), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('niveau', sa.String(length=20), nullable=False),
    sa.Column('titre', sa.String(length=300), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('lien', sa.String(length=300), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('traitee', sa.Boolean(), nullable=False),
    sa.Column('traitee_par_id', sa.Integer(), nullable=True),
    sa.Column('traitee_le', sa.DateTime(), nullable=True),
    sa.Column('notifiee_le', sa.DateTime(), nullable=True),
    sa.Column('erreur_notification', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['traitee_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cle')
    )
    op.create_index(op.f('ix_alertes_client_id'), 'alertes', ['client_id'], unique=False)
    op.create_index(op.f('ix_alertes_cree_le'), 'alertes', ['cree_le'], unique=False)
    op.create_index(op.f('ix_alertes_traitee'), 'alertes', ['traitee'], unique=False)
    op.create_table('contrats',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('produit', sa.String(length=20), nullable=False),
    sa.Column('reference', sa.String(length=200), nullable=False),
    sa.Column('licences', sa.Integer(), nullable=False),
    sa.Column('debut', sa.Date(), nullable=True),
    sa.Column('echeance', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contrats_client_id'), 'contrats', ['client_id'], unique=False)
    op.create_index(op.f('ix_contrats_echeance'), 'contrats', ['echeance'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_contrats_echeance'), table_name='contrats')
    op.drop_index(op.f('ix_contrats_client_id'), table_name='contrats')
    op.drop_table('contrats')
    op.drop_index(op.f('ix_alertes_traitee'), table_name='alertes')
    op.drop_index(op.f('ix_alertes_cree_le'), table_name='alertes')
    op.drop_index(op.f('ix_alertes_client_id'), table_name='alertes')
    op.drop_table('alertes')
    op.drop_table('envois')
