"""Sécurité : verrouillage après échecs, version de session, double authentification (TOTP),
journal d'audit chaîné par empreinte SHA-256

Révision : 0006
Précédente : 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('utilisateurs', sa.Column('echecs_connexion', sa.Integer(), server_default='0', nullable=False))
    op.add_column('utilisateurs', sa.Column('bloque_jusqua', sa.DateTime(), nullable=True))
    op.add_column('utilisateurs', sa.Column('version_session', sa.Integer(), server_default='1', nullable=False))
    op.add_column('utilisateurs', sa.Column('totp_secret', sa.String(length=64), nullable=True))
    op.add_column('utilisateurs', sa.Column('totp_actif', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('utilisateurs', sa.Column('totp_dernier_pas', sa.Integer(), nullable=True))

    op.add_column('journal', sa.Column('acteur', sa.String(length=200), server_default='', nullable=False))
    op.add_column('journal', sa.Column('empreinte_precedente', sa.String(length=64), nullable=True))
    op.add_column('journal', sa.Column('empreinte', sa.String(length=64), nullable=True))
    # Supprimer un compte ne doit pas supprimer (ni bloquer) ses lignes de journal
    op.drop_constraint('journal_utilisateur_id_fkey', 'journal', type_='foreignkey')
    op.create_foreign_key('journal_utilisateur_id_fkey', 'journal', 'utilisateurs', ['utilisateur_id'], ['id'], ondelete='SET NULL')

    # Reprise de l'existant : acteur figé, puis chaînage de toutes les lignes dans l'ordre
    op.execute("UPDATE journal j SET acteur = u.email FROM utilisateurs u WHERE j.utilisateur_id = u.id")
    op.execute("UPDATE journal SET acteur = 'système' WHERE acteur = ''")
    from app.integrite import ORIGINE, empreinte
    connexion = op.get_bind()
    precedente = ORIGINE
    lignes = connexion.execute(sa.text("SELECT id, quand, acteur, action, detail FROM journal ORDER BY id")).all()
    for l in lignes:
        valeur = empreinte(precedente, l.id, l.quand, l.acteur, l.action, l.detail)
        connexion.execute(sa.text("UPDATE journal SET empreinte_precedente = :p, empreinte = :e WHERE id = :i"),
                          {"p": precedente, "e": valeur, "i": l.id})
        precedente = valeur


def downgrade():
    op.drop_constraint('journal_utilisateur_id_fkey', 'journal', type_='foreignkey')
    op.create_foreign_key('journal_utilisateur_id_fkey', 'journal', 'utilisateurs', ['utilisateur_id'], ['id'])
    for colonne in ('empreinte', 'empreinte_precedente', 'acteur'):
        op.drop_column('journal', colonne)
    for colonne in ('totp_dernier_pas', 'totp_actif', 'totp_secret', 'version_session', 'bloque_jusqua', 'echecs_connexion'):
        op.drop_column('utilisateurs', colonne)
