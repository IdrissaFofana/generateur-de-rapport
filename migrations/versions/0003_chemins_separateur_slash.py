"""Chemins de stockage enregistrés sous Windows (« hebdos\\x.pdf ») convertis au format « hebdos/x.pdf »

Révision : 0003
Précédente : 0002
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

COLONNES = [("hebdos", "chemin"), ("exports_ksc", "chemin"), ("rapports", "pdf")]


def upgrade():
    for table, colonne in COLONNES:
        op.execute(f"UPDATE {table} SET {colonne} = replace({colonne}, chr(92), '/') WHERE strpos({colonne}, chr(92)) > 0")


def downgrade():
    pass  # « / » fonctionne sur tous les systèmes : rien à défaire
