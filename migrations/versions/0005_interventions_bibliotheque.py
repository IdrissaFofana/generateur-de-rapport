"""Rapports d'intervention, bibliothèque d'actions et de recommandations, code et destinataires des clients

Révision : 0005
Précédente : 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

# Bibliothèque de départ (terminologie Kaspersky Security Center / Endpoint Security / EDR / MDR).
# (type d'intervention, genre, catégorie, libellé) — « tous » : proposé pour tous les types.
BIBLIOTHEQUE = [
    # ------------------------------------------------------------------ Déploiement
    ("deploiement", "action", "Serveur d'administration", "Installation du Serveur d'administration Kaspersky Security Center"),
    ("deploiement", "action", "Serveur d'administration", "Exécution de l'assistant de configuration initiale du Serveur d'administration"),
    ("deploiement", "action", "Serveur d'administration", "Activation de la licence sur le Serveur d'administration"),
    ("deploiement", "action", "Serveur d'administration", "Création de la structure des groupes d'administration"),
    ("deploiement", "action", "Serveur d'administration", "Configuration des règles de déplacement automatique des appareils vers les groupes"),
    ("deploiement", "action", "Serveur d'administration", "Sondage du réseau (Active Directory et plages d'adresses IP)"),
    ("deploiement", "action", "Paquets d'installation", "Génération d'un paquet d'installation autonome combiné KES + Agent d'administration"),
    ("deploiement", "action", "Paquets d'installation", "Génération d'un paquet autonome combiné KES + Agent d'administration + module MDR"),
    ("deploiement", "action", "Paquets d'installation", "Création du paquet d'installation de l'Agent d'administration"),
    ("deploiement", "action", "Points de distribution", "Désignation des points de distribution par plage d'adresses"),
    ("deploiement", "action", "Points de distribution", "Génération des paquets de points de distribution pour chaque plage d'adresses"),
    ("deploiement", "action", "Installation", "Création et exécution de la tâche d'installation à distance de Kaspersky Endpoint Security"),
    ("deploiement", "action", "Installation", "Déploiement de l'Agent d'administration par stratégie de groupe Active Directory (GPO)"),
    ("deploiement", "action", "Installation", "Installation manuelle de KES sur les postes non joignables à distance"),
    ("deploiement", "action", "Installation", "Désinstallation des solutions antivirus incompatibles"),
    ("deploiement", "action", "Stratégies", "Création et configuration de la stratégie Kaspersky Endpoint Security"),
    ("deploiement", "action", "Stratégies", "Création de la stratégie de l'Agent d'administration"),
    ("deploiement", "action", "Stratégies", "Configuration des exclusions et des applications de confiance"),
    ("deploiement", "action", "Stratégies", "Activation de Kaspersky Security Network (KSN) dans la stratégie"),
    ("deploiement", "action", "Stratégies", "Modification de la stratégie de groupe pour intégrer le module MDR"),
    ("deploiement", "action", "Tâches", "Création d'une tâche de mise à jour des bases pour l'ensemble du parc"),
    ("deploiement", "action", "Tâches", "Création d'une tâche d'analyse complète planifiée"),
    ("deploiement", "action", "Tâches", "Création d'une tâche de recherche de vulnérabilités et de mises à jour requises pour les postes, planifiée chaque lundi"),
    ("deploiement", "action", "Tâches", "Création d'une tâche de recherche de vulnérabilités et de mises à jour requises pour les serveurs, planifiée chaque samedi"),
    ("deploiement", "action", "Tâches", "Création d'une tâche de sauvegarde des données du Serveur d'administration"),
    ("deploiement", "action", "EDR / MDR", "Activation du module EDR Optimum dans la stratégie Kaspersky Endpoint Security"),
    ("deploiement", "action", "EDR / MDR", "Création d'une tâche de modification des composants de l'application pour intégrer le MDR"),
    ("deploiement", "action", "EDR / MDR", "Import du fichier de configuration MDR et activation du service"),
    ("deploiement", "action", "EDR / MDR", "Configuration du MDR"),
    ("deploiement", "action", "EDR / MDR", "Vérification de la remontée de la télémétrie dans la console MDR"),
    ("deploiement", "action", "Vérifications", "Vérification de l'état de protection des appareils dans la console"),
    ("deploiement", "action", "Vérifications", "Contrôle de la connexion des appareils au Serveur d'administration"),
    ("deploiement", "recommandation", "Réseau", "Ouvrir les ports 135, 139 et 445 (et 13000, 14000, 15000) pour permettre l'installation à distance"),
    ("deploiement", "recommandation", "Réseau", "Autoriser l'accès aux serveurs KSN sur le pare-feu ou le proxy"),
    ("deploiement", "recommandation", "Parc", "Désinstaller les solutions antivirus tierces restantes avant la suite du déploiement"),
    ("deploiement", "recommandation", "Parc", "Déployer la protection sur les postes nomades lors de leur prochaine connexion au réseau"),
    ("deploiement", "recommandation", "Organisation", "Désigner un référent interne pour le suivi de la console Kaspersky Security Center"),
    # ------------------------------------------------------------------ Migration
    ("migration", "action", "Préparation", "Sauvegarde des données du Serveur d'administration (utilitaire klbackup)"),
    ("migration", "action", "Préparation", "Inventaire des stratégies, tâches et paquets d'installation existants"),
    ("migration", "action", "Nouveau serveur", "Installation du nouveau Serveur d'administration Kaspersky Security Center"),
    ("migration", "action", "Nouveau serveur", "Restauration des données sur le nouveau Serveur d'administration"),
    ("migration", "action", "Nouveau serveur", "Installation et configuration de Kaspersky Security Center Web Console"),
    ("migration", "action", "Bascule", "Réaffectation des Agents d'administration vers le nouveau serveur (utilitaire klmover)"),
    ("migration", "action", "Bascule", "Vérification de la connexion des appareils au nouveau Serveur d'administration"),
    ("migration", "action", "Bascule", "Vérification des stratégies et des tâches après migration"),
    ("migration", "action", "Bascule", "Mise hors service de l'ancien Serveur d'administration"),
    ("migration", "recommandation", "Sécurité", "Conserver la sauvegarde de l'ancien Serveur d'administration pendant 30 jours"),
    ("migration", "recommandation", "Sécurité", "Planifier une tâche de sauvegarde régulière du nouveau Serveur d'administration"),
    # ------------------------------------------------------------------ Maintenance
    ("maintenance", "action", "Mises à jour", "Mise à jour du Serveur d'administration Kaspersky Security Center"),
    ("maintenance", "action", "Mises à jour", "Mise à jour de Kaspersky Endpoint Security vers la dernière version"),
    ("maintenance", "action", "Mises à jour", "Mise à jour de l'Agent d'administration"),
    ("maintenance", "action", "Mises à jour", "Contrôle de la mise à jour des bases antivirus sur le parc"),
    ("maintenance", "action", "Licences", "Vérification et renouvellement de la clé de licence"),
    ("maintenance", "action", "Console", "Nettoyage des appareils inactifs de la console"),
    ("maintenance", "action", "Console", "Affectation des appareils non affectés aux groupes d'administration"),
    ("maintenance", "action", "Console", "Vérification de l'exécution des tâches planifiées"),
    ("maintenance", "action", "Console", "Analyse des événements critiques du Serveur d'administration"),
    ("maintenance", "action", "Serveur", "Vérification de l'espace disque et de la base de données du Serveur d'administration"),
    ("maintenance", "action", "Serveur", "Vérification de la tâche de sauvegarde du Serveur d'administration"),
    ("maintenance", "recommandation", "Parc", "Planifier le remplacement des postes Windows 10 (fin de support le 14/10/2025)"),
    ("maintenance", "recommandation", "Console", "Supprimer de la console les appareils inactifs depuis plus de 60 jours"),
    ("maintenance", "recommandation", "Vulnérabilités", "Mettre en place la tâche d'installation des mises à jour requises et de correction des vulnérabilités"),
    ("maintenance", "recommandation", "Licences", "Prévoir le renouvellement de la licence avant son échéance"),
    # ------------------------------------------------------------------ Assistance
    ("assistance", "action", "Diagnostic", "Diagnostic d'un appareil en état critique"),
    ("assistance", "action", "Diagnostic", "Collecte des traces (GetSystemInfo) et ouverture d'un ticket auprès du support Kaspersky"),
    ("assistance", "action", "Correction", "Réinstallation de l'Agent d'administration sur l'appareil"),
    ("assistance", "action", "Correction", "Rétablissement de la connexion de l'appareil au Serveur d'administration"),
    ("assistance", "action", "Correction", "Mise à jour manuelle des bases antivirus"),
    ("assistance", "action", "Correction", "Ajout d'une exclusion pour une application métier"),
    ("assistance", "action", "Correction", "Déblocage d'une application ou d'un site web bloqué à tort"),
    ("assistance", "action", "Correction", "Restauration d'un fichier depuis la quarantaine"),
    ("assistance", "recommandation", "Suivi", "Vérifier la connectivité réseau de l'appareil vers le Serveur d'administration (ports 13000 et 14000)"),
    ("assistance", "recommandation", "Suivi", "Recontacter le support ESAY si le problème se reproduit"),
    # ------------------------------------------------------------------ Incident
    ("incident", "action", "Confinement", "Isolement réseau de l'appareil compromis"),
    ("incident", "action", "Confinement", "Blocage de l'exécution du fichier malveillant par son empreinte (hash)"),
    ("incident", "action", "Analyse", "Analyse de l'incident dans la console MDR"),
    ("incident", "action", "Analyse", "Analyse complète de l'appareil avec des bases à jour"),
    ("incident", "action", "Analyse", "Recherche de l'indicateur de compromission (IOC) sur l'ensemble du parc"),
    ("incident", "action", "Remédiation", "Application des mesures de réponse recommandées par le SOC Kaspersky"),
    ("incident", "action", "Remédiation", "Suppression ou mise en quarantaine des objets malveillants"),
    ("incident", "action", "Remédiation", "Réinitialisation des comptes utilisateurs potentiellement compromis"),
    ("incident", "action", "Remédiation", "Levée de l'isolement réseau après validation"),
    ("incident", "recommandation", "Comptes", "Changer les mots de passe des comptes exposés"),
    ("incident", "recommandation", "Correctifs", "Appliquer les correctifs de sécurité de l'application exploitée"),
    ("incident", "recommandation", "Utilisateurs", "Sensibiliser les utilisateurs au hameçonnage (phishing)"),
    ("incident", "recommandation", "Comptes", "Renforcer la politique de mots de passe"),
    # ------------------------------------------------------------------ Audit
    ("audit", "action", "Configuration", "Revue de la configuration du Serveur d'administration"),
    ("audit", "action", "Configuration", "Revue des stratégies de protection (KES et Agent d'administration)"),
    ("audit", "action", "Configuration", "Revue des exclusions configurées"),
    ("audit", "action", "Parc", "Inventaire des appareils administrés et non administrés"),
    ("audit", "action", "Parc", "Contrôle de la couverture de protection du parc"),
    ("audit", "action", "Parc", "Contrôle de la couverture MDR (télémétrie)"),
    ("audit", "action", "Vulnérabilités", "Analyse des vulnérabilités logicielles"),
    ("audit", "action", "Accès", "Revue des comptes et des droits d'accès à la console"),
    ("audit", "recommandation", "Configuration", "Supprimer les exclusions trop larges"),
    ("audit", "recommandation", "Parc", "Installer la protection sur les appareils non administrés"),
    ("audit", "recommandation", "Accès", "Appliquer le principe du moindre privilège aux comptes de la console"),
    # ------------------------------------------------------------------ Formation
    ("formation", "action", "Console", "Présentation de l'interface de Kaspersky Security Center"),
    ("formation", "action", "Console", "Gestion des groupes d'administration et des stratégies"),
    ("formation", "action", "Suivi", "Consultation et interprétation des rapports"),
    ("formation", "action", "Suivi", "Traitement des événements et des alertes"),
    ("formation", "action", "MDR", "Présentation de la console MDR et du traitement des incidents"),
    ("formation", "action", "Support", "Remise du support de formation"),
    ("formation", "recommandation", "Organisation", "Désigner un référent interne formé à la console"),
    ("formation", "recommandation", "Organisation", "Planifier une session d'approfondissement"),
]


def upgrade():
    op.add_column('clients', sa.Column('code', sa.String(length=10), nullable=True))
    op.add_column('clients', sa.Column('emails_rapports', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.create_table('interventions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.String(length=40), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('annee', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('interlocuteur', sa.String(length=300), nullable=False),
    sa.Column('intervenants', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('date_debut', sa.Date(), nullable=False),
    sa.Column('date_fin', sa.Date(), nullable=False),
    sa.Column('heure_debut', sa.Time(), nullable=True),
    sa.Column('heure_fin', sa.Time(), nullable=True),
    sa.Column('objet', sa.Text(), nullable=False),
    sa.Column('contexte', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('travaux', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('resultat', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('statut_global', sa.String(length=20), nullable=False),
    sa.Column('points_bloquants', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('recommandations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('statut', sa.String(length=20), nullable=False),
    sa.Column('pdf', sa.String(length=500), nullable=True),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('modifie_le', sa.DateTime(), nullable=True),
    sa.Column('valide_par_id', sa.Integer(), nullable=True),
    sa.Column('valide_le', sa.DateTime(), nullable=True),
    sa.Column('envoye_le', sa.DateTime(), nullable=True),
    sa.Column('envoye_a', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ),
    sa.ForeignKeyConstraint(['valide_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id', 'annee', 'sequence'),
    sa.UniqueConstraint('numero')
    )
    op.create_index(op.f('ix_interventions_client_id'), 'interventions', ['client_id'], unique=False)
    op.create_index(op.f('ix_interventions_date_debut'), 'interventions', ['date_debut'], unique=False)
    bibliotheque = op.create_table('bibliotheque',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('genre', sa.String(length=20), nullable=False),
    sa.Column('type_intervention', sa.String(length=20), nullable=False),
    sa.Column('categorie', sa.String(length=100), nullable=False),
    sa.Column('libelle', sa.Text(), nullable=False),
    sa.Column('ordre', sa.Integer(), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.Column('cree_par_id', sa.Integer(), nullable=True),
    sa.Column('cree_le', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cree_par_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bibliotheque_type_intervention'), 'bibliotheque', ['type_intervention'], unique=False)
    op.bulk_insert(bibliotheque, [
        {"type_intervention": t, "genre": g, "categorie": c, "libelle": l, "ordre": (i + 1) * 10, "actif": True}
        for i, (t, g, c, l) in enumerate(BIBLIOTHEQUE)])


def downgrade():
    op.drop_index(op.f('ix_bibliotheque_type_intervention'), table_name='bibliotheque')
    op.drop_table('bibliotheque')
    op.drop_index(op.f('ix_interventions_date_debut'), table_name='interventions')
    op.drop_index(op.f('ix_interventions_client_id'), table_name='interventions')
    op.drop_table('interventions')
    op.drop_column('clients', 'emails_rapports')
    op.drop_column('clients', 'code')
