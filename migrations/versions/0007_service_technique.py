"""Service technique : assistances mensuelles planifiées, parcours et certifications des techniciens,
activités internes, rapports du service, import d'anciens rapports d'intervention

Révision : 0007
Précédente : 0006
Créée le : 2026-09-30 11:37:43.680443
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('activites_internes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('titre', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('participants', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('duree_heures', sa.Float(), nullable=True),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activites_internes_date'), 'activites_internes', ['date'], unique=False)
    op.create_table('certifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=False),
    sa.Column('intitule', sa.String(length=300), nullable=False),
    sa.Column('editeur', sa.String(length=100), nullable=False),
    sa.Column('numero', sa.String(length=100), nullable=False),
    sa.Column('obtenue_le', sa.Date(), nullable=False),
    sa.Column('expire_le', sa.Date(), nullable=True),
    sa.Column('fichier', sa.String(length=500), nullable=True),
    sa.Column('nom_fichier', sa.String(length=300), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_certifications_expire_le'), 'certifications', ['expire_le'], unique=False)
    op.create_index(op.f('ix_certifications_utilisateur_id'), 'certifications', ['utilisateur_id'], unique=False)
    op.create_table('formations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utilisateur_id', sa.Integer(), nullable=False),
    sa.Column('intitule', sa.String(length=300), nullable=False),
    sa.Column('organisme', sa.String(length=200), nullable=False),
    sa.Column('debut', sa.Date(), nullable=True),
    sa.Column('fin', sa.Date(), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('heures', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_formations_utilisateur_id'), 'formations', ['utilisateur_id'], unique=False)
    op.create_table('rapports_service',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('periodicite', sa.String(length=20), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('debut', sa.Date(), nullable=False),
    sa.Column('fin', sa.Date(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('donnees', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('contenu', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pdf', sa.String(length=500), nullable=True),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('valide_par_id', sa.Integer(), nullable=True),
    sa.Column('valide_le', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['valide_par_id'], ['utilisateurs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('periodicite', 'annee', 'numero', 'version')
    )
    op.create_table('assistances_planifiees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=False),
    sa.Column('mois', sa.Integer(), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('date_prevue', sa.Date(), nullable=True),
    sa.Column('technicien_id', sa.Integer(), nullable=True),
    sa.Column('intervention_id', sa.Integer(), nullable=True),
    sa.Column('justification', sa.Text(), nullable=False),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['intervention_id'], ['interventions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['technicien_id'], ['utilisateurs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id', 'annee', 'mois')
    )
    op.create_index(op.f('ix_assistances_planifiees_client_id'), 'assistances_planifiees', ['client_id'], unique=False)
    op.add_column('clients', sa.Column('assistance_mensuelle', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('clients', sa.Column('assistance_depuis', sa.Date(), nullable=True))
    op.add_column('interventions', sa.Column('source', sa.String(length=20), server_default='saisie', nullable=False))
    op.add_column('interventions', sa.Column('fichier_source', sa.String(length=500), nullable=True))
    op.add_column('interventions', sa.Column('nom_fichier_source', sa.String(length=300), nullable=True))
    op.add_column('interventions', sa.Column('texte_source', sa.Text(), nullable=True))
    op.add_column('interventions', sa.Column('a_verifier', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('interventions', 'a_verifier')
    op.drop_column('interventions', 'texte_source')
    op.drop_column('interventions', 'nom_fichier_source')
    op.drop_column('interventions', 'fichier_source')
    op.drop_column('interventions', 'source')
    op.drop_column('clients', 'assistance_depuis')
    op.drop_column('clients', 'assistance_mensuelle')
    op.drop_index(op.f('ix_assistances_planifiees_client_id'), table_name='assistances_planifiees')
    op.drop_table('assistances_planifiees')
    op.drop_table('rapports_service')
    op.drop_index(op.f('ix_formations_utilisateur_id'), table_name='formations')
    op.drop_table('formations')
    op.drop_index(op.f('ix_certifications_utilisateur_id'), table_name='certifications')
    op.drop_index(op.f('ix_certifications_expire_le'), table_name='certifications')
    op.drop_table('certifications')
    op.drop_index(op.f('ix_activites_internes_date'), table_name='activites_internes')
    op.drop_table('activites_internes')
