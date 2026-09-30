"""Schéma initial (tables existantes avant l'introduction des migrations)

Révision : 0001
Précédente : 
Créée le : 2026-09-29 12:54:18.609113
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.Column('avec_mdr', sa.Boolean(), nullable=False),
    sa.Column('avec_ksc', sa.Boolean(), nullable=False),
    sa.Column('suggerer_mdr', sa.Boolean(), nullable=False),
    sa.Column('tenants_mdr', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nom')
    )
    op.create_table('utilisateurs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.Column('mot_de_passe', sa.String(length=300), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.Column('doit_changer_mdp', sa.Boolean(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('derniere_connexion', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_utilisateurs_email'), 'utilisateurs', ['email'], unique=True)
    op.create_table('exports_ksc',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=False),
    sa.Column('mois', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=True),
    sa.Column('fichier', sa.String(length=300), nullable=False),
    sa.Column('chemin', sa.String(length=500), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('genere_le', sa.DateTime(), nullable=True),
    sa.Column('donnees', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('erreur', sa.Text(), nullable=True),
    sa.Column('remplace', sa.Boolean(), nullable=False),
    sa.Column('depose_par_id', sa.Integer(), nullable=True),
    sa.Column('depose_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['depose_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exports_ksc_client_id'), 'exports_ksc', ['client_id'], unique=False)
    op.create_table('hebdos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fichier', sa.String(length=300), nullable=False),
    sa.Column('chemin', sa.String(length=500), nullable=False),
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('debut', sa.Date(), nullable=True),
    sa.Column('fin', sa.Date(), nullable=True),
    sa.Column('donnees', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('erreur', sa.Text(), nullable=True),
    sa.Column('depose_par_id', sa.Integer(), nullable=True),
    sa.Column('depose_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['depose_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('empreinte')
    )
    op.create_index(op.f('ix_hebdos_debut'), 'hebdos', ['debut'], unique=False)
    op.create_table('journal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('quand', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_journal_quand'), 'journal', ['quand'], unique=False)
    op.create_table('rapports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('periodicite', sa.String(length=20), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=False),
    sa.Column('mois', sa.Integer(), nullable=False),
    sa.Column('debut', sa.Date(), nullable=False),
    sa.Column('fin', sa.Date(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('profil', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('donnees', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('contenu', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('indicateurs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pdf', sa.String(length=500), nullable=True),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('modifie_le', sa.DateTime(), nullable=True),
    sa.Column('valide_par_id', sa.Integer(), nullable=True),
    sa.Column('valide_le', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ),
    sa.ForeignKeyConstraint(['valide_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id', 'periodicite', 'debut', 'version')
    )
    op.create_index(op.f('ix_rapports_client_id'), 'rapports', ['client_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_rapports_client_id'), table_name='rapports')
    op.drop_table('rapports')
    op.drop_index(op.f('ix_journal_quand'), table_name='journal')
    op.drop_table('journal')
    op.drop_index(op.f('ix_hebdos_debut'), table_name='hebdos')
    op.drop_table('hebdos')
    op.drop_index(op.f('ix_exports_ksc_client_id'), table_name='exports_ksc')
    op.drop_table('exports_ksc')
    op.drop_index(op.f('ix_utilisateurs_email'), table_name='utilisateurs')
    op.drop_table('utilisateurs')
    op.drop_table('clients')
