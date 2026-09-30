"""Modèle de données."""
from datetime import date, datetime, time

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLES = {
    "admin": "Administrateur",
    "validateur": "Validateur",
    "operateur": "Opérateur",
    "lecteur": "Lecteur",
}
# Ce que chaque rôle peut faire (un rôle hérite des droits des rôles inférieurs)
NIVEAUX = {"lecteur": 1, "operateur": 2, "validateur": 3, "admin": 4}

TYPES_EXPORT = {
    "protection": "État de la protection",
    "menaces": "Menaces",
    "vulnerabilites": "Vulnérabilités",
}
# Statuts d'analyse d'un fichier déposé
EN_ATTENTE, EN_COURS, ANALYSE_OK, ERREUR = "en_attente", "en_cours", "ok", "erreur"
# Statuts d'un rapport
BROUILLON, VALIDE = "brouillon", "valide"


class Utilisateur(Base):
    __tablename__ = "utilisateurs"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(200))
    mot_de_passe: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="lecteur")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    doit_changer_mdp: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    derniere_connexion: Mapped[datetime | None] = mapped_column(DateTime)
    # Protection contre la force brute : échecs consécutifs et verrouillage temporaire
    echecs_connexion: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bloque_jusqua: Mapped[datetime | None] = mapped_column(DateTime)
    # Incrémentée à chaque changement sensible : invalide les sessions ouvertes ailleurs
    version_session: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Double authentification (TOTP) ; dernier pas accepté pour refuser le rejeu d'un code
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_actif: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_dernier_pas: Mapped[int | None] = mapped_column(Integer)

    def peut(self, role_minimum):
        return self.actif and NIVEAUX[self.role] >= NIVEAUX[role_minimum]

    @property
    def libelle_role(self):
        return ROLES[self.role]


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200), unique=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    avec_mdr: Mapped[bool] = mapped_column(Boolean, default=True)
    avec_ksc: Mapped[bool] = mapped_column(Boolean, default=True)
    suggerer_mdr: Mapped[bool] = mapped_column(Boolean, default=False)
    # Noms des tenants MDR tels qu'ils apparaissent dans les rapports hebdo (« root tenant » pour le tenant racine)
    tenants_mdr: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Code court des numéros de rapport d'intervention (RI-2026-HUD-004) et destinataires des rapports
    code: Mapped[str | None] = mapped_column(String(10))
    emails_rapports: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # Autres écritures du nom (sigle, nom complet, ancien nom) : reconnaissance des documents importés
    autres_noms: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # Assistance mensuelle : au moins une assistance par mois, planifiée automatiquement
    assistance_mensuelle: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    assistance_depuis: Mapped[date | None] = mapped_column(Date)
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def code_rapport(self):
        """Code du client dans les numéros : saisi dans sa fiche, sinon 3 premières lettres du nom."""
        if self.code:
            return self.code.upper()
        lettres = "".join(ch for ch in self.nom.upper() if ch.isalnum())
        return (lettres[:3] or "CLI")

    @property
    def profil(self):
        if self.avec_mdr and self.avec_ksc:
            return "MDR + KSC"
        return "MDR seul" if self.avec_mdr else "KSC seul"


class Hebdo(Base):
    """Rapport hebdomadaire Kaspersky MDR (tous clients)."""
    __tablename__ = "hebdos"
    id: Mapped[int] = mapped_column(primary_key=True)
    fichier: Mapped[str] = mapped_column(String(300))
    chemin: Mapped[str] = mapped_column(String(500))
    empreinte: Mapped[str] = mapped_column(String(64), unique=True)
    debut: Mapped[date | None] = mapped_column(Date, index=True)
    fin: Mapped[date | None] = mapped_column(Date)
    donnees: Mapped[dict | None] = mapped_column(JSONB)
    statut: Mapped[str] = mapped_column(String(20), default=EN_ATTENTE)
    erreur: Mapped[str | None] = mapped_column(Text)
    depose_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    depose_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    depose_par = relationship("Utilisateur")


class ExportKsc(Base):
    """Export Kaspersky Security Center d'un client pour un mois."""
    __tablename__ = "exports_ksc"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    annee: Mapped[int] = mapped_column(Integer)
    mois: Mapped[int] = mapped_column(Integer)
    type: Mapped[str | None] = mapped_column(String(20))
    fichier: Mapped[str] = mapped_column(String(300))
    chemin: Mapped[str] = mapped_column(String(500))
    empreinte: Mapped[str] = mapped_column(String(64))
    genere_le: Mapped[datetime | None] = mapped_column(DateTime)
    donnees: Mapped[dict | None] = mapped_column(JSONB)
    statut: Mapped[str] = mapped_column(String(20), default=EN_ATTENTE)
    erreur: Mapped[str | None] = mapped_column(Text)
    remplace: Mapped[bool] = mapped_column(Boolean, default=False)  # remplacé par un dépôt plus récent
    depose_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    depose_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    client = relationship("Client")
    depose_par = relationship("Utilisateur")


class Rapport(Base):
    """Une version de rapport (mensuel en V1 ; trimestriel/semestriel/annuel en V2)."""
    __tablename__ = "rapports"
    __table_args__ = (UniqueConstraint("client_id", "periodicite", "debut", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    periodicite: Mapped[str] = mapped_column(String(20), default="mensuel")
    annee: Mapped[int] = mapped_column(Integer)
    mois: Mapped[int] = mapped_column(Integer)  # mois de début de période
    debut: Mapped[date] = mapped_column(Date)
    fin: Mapped[date] = mapped_column(Date)  # exclue
    version: Mapped[int] = mapped_column(Integer, default=1)
    statut: Mapped[str] = mapped_column(String(20), default=BROUILLON)
    profil: Mapped[dict] = mapped_column(JSONB)          # profil du client au moment du rapport
    donnees: Mapped[dict] = mapped_column(JSONB)         # données consolidées (chiffres, tableaux)
    contenu: Mapped[dict] = mapped_column(JSONB)         # textes et actions modifiables
    indicateurs: Mapped[dict] = mapped_column(JSONB)     # indicateurs clés (évolutions, bilans)
    pdf: Mapped[str | None] = mapped_column(String(500))
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    modifie_le: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
    valide_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    valide_le: Mapped[datetime | None] = mapped_column(DateTime)
    client = relationship("Client")
    cree_par = relationship("Utilisateur", foreign_keys=[cree_par_id])
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])


class Journal(Base):
    """Traçabilité : qui a fait quoi. Lignes chaînées par empreinte SHA-256 (voir app/integrite.py)."""
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"), index=True)
    acteur: Mapped[str] = mapped_column(String(200), default="", server_default="")  # e-mail figé au moment de l'action
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    quand: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    empreinte_precedente: Mapped[str | None] = mapped_column(String(64))
    empreinte: Mapped[str | None] = mapped_column(String(64))
    utilisateur = relationship("Utilisateur")


PRODUITS = {"KSC": "Kaspersky Security Center (EDR / protection)", "MDR": "Kaspersky MDR", "Autre": "Autre"}


class Contrat(Base):
    """Contrat / lot de licences d'un client : comparé à l'usage réel (appareils KSC, postes MDR)."""
    __tablename__ = "contrats"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    produit: Mapped[str] = mapped_column(String(20), default="KSC")
    reference: Mapped[str] = mapped_column(String(200), default="")
    licences: Mapped[int] = mapped_column(Integer, default=0)
    debut: Mapped[date | None] = mapped_column(Date)
    echeance: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    client = relationship("Client")


# Niveaux d'alerte, du plus grave au moins grave
NIVEAUX_ALERTE = {"critique": "Critique", "avertissement": "Avertissement", "info": "Information"}


class Alerte(Base):
    """Événement à signaler (niveau critique, hausse des détections, incident MDR, licences…).
    La clé rend chaque alerte unique : une même situation n'est signalée qu'une fois."""
    __tablename__ = "alertes"
    id: Mapped[int] = mapped_column(primary_key=True)
    cle: Mapped[str] = mapped_column(String(200), unique=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    niveau: Mapped[str] = mapped_column(String(20), default="avertissement")
    titre: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    lien: Mapped[str] = mapped_column(String(300), default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    traitee: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    traitee_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    traitee_le: Mapped[datetime | None] = mapped_column(DateTime)
    notifiee_le: Mapped[datetime | None] = mapped_column(DateTime)
    erreur_notification: Mapped[str | None] = mapped_column(Text)
    client = relationship("Client")
    traitee_par = relationship("Utilisateur")


class Envoi(Base):
    """Envois périodiques déjà faits (ex. résumé hebdomadaire d'une semaine) : pas de doublon."""
    __tablename__ = "envois"
    __table_args__ = (UniqueConstraint("type", "periode"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    periode: Mapped[str] = mapped_column(String(20))
    envoye_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    detail: Mapped[str] = mapped_column(Text, default="")


# --------------------------------------------------------------------------- #
# Rapports d'intervention
# --------------------------------------------------------------------------- #
TYPES_INTERVENTION = {  # clé : (libellé du type, titre du document)
    "deploiement": ("Déploiement", "Rapport de déploiement"),
    "migration": ("Migration", "Rapport de migration"),
    "maintenance": ("Maintenance", "Rapport de maintenance"),
    "assistance": ("Assistance", "Rapport d'assistance"),
    "incident": ("Incident", "Rapport d'intervention sur incident"),
    "audit": ("Audit", "Rapport d'audit"),
    "formation": ("Formation", "Rapport de formation"),
}
MODES_INTERVENTION = {"site": "Sur site", "distance": "À distance"}
STATUTS_INTERVENTION = ("OK", "Partiel", "Échec")


class Intervention(Base):
    """Intervention chez un client : saisie au retour, validée (PDF archivé) puis envoyée au client."""
    __tablename__ = "interventions"
    __table_args__ = (UniqueConstraint("client_id", "annee", "sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    annee: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(20), default="site")
    interlocuteur: Mapped[str] = mapped_column(String(300), default="")
    intervenants: Mapped[list] = mapped_column(JSONB, default=list)
    date_debut: Mapped[date] = mapped_column(Date, index=True)
    date_fin: Mapped[date] = mapped_column(Date)
    heure_debut: Mapped[time | None] = mapped_column(Time)
    heure_fin: Mapped[time | None] = mapped_column(Time)
    objet: Mapped[str] = mapped_column(Text, default="")
    contexte: Mapped[dict] = mapped_column(JSONB, default=dict)       # postes, serveurs, systemes, version_ksc, autres
    travaux: Mapped[list] = mapped_column(JSONB, default=list)        # [{module, resultat, actions}]
    resultat: Mapped[list] = mapped_column(JSONB, default=list)       # actions réalisées (puces), issues de la bibliothèque
    statut_global: Mapped[str] = mapped_column(String(20), default="OK")
    points_bloquants: Mapped[list] = mapped_column(JSONB, default=list)  # [{probleme, impact, action, responsable, echeance, plan_action}]
    recommandations: Mapped[list] = mapped_column(JSONB, default=list)
    statut: Mapped[str] = mapped_column(String(20), default=BROUILLON)
    pdf: Mapped[str | None] = mapped_column(String(500))
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    modifie_le: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
    valide_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    valide_le: Mapped[datetime | None] = mapped_column(DateTime)
    envoye_le: Mapped[datetime | None] = mapped_column(DateTime)
    envoye_a: Mapped[str] = mapped_column(Text, default="")
    # Provenance : saisie dans la plateforme ou import d'un ancien rapport (fichier d'origine conservé)
    source: Mapped[str] = mapped_column(String(20), default="saisie", server_default="saisie")
    fichier_source: Mapped[str | None] = mapped_column(String(500))
    nom_fichier_source: Mapped[str | None] = mapped_column(String(300))
    texte_source: Mapped[str | None] = mapped_column(Text)
    a_verifier: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    client = relationship("Client")
    cree_par = relationship("Utilisateur", foreign_keys=[cree_par_id])
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])

    @property
    def libelle_type(self):
        return TYPES_INTERVENTION.get(self.type, (self.type, ""))[0]

    @property
    def titre(self):
        return TYPES_INTERVENTION.get(self.type, ("", "Rapport d'intervention"))[1]


class ElementBibliotheque(Base):
    """Action type ou recommandation type, proposée selon le type d'intervention (« tous » : proposée partout)."""
    __tablename__ = "bibliotheque"
    id: Mapped[int] = mapped_column(primary_key=True)
    genre: Mapped[str] = mapped_column(String(20), default="action")   # action | recommandation
    type_intervention: Mapped[str] = mapped_column(String(20), index=True)
    categorie: Mapped[str] = mapped_column(String(100), default="")
    libelle: Mapped[str] = mapped_column(Text)
    ordre: Mapped[int] = mapped_column(Integer, default=100)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --------------------------------------------------------------------------- #
# Service technique : assistances mensuelles, techniciens, activités internes, rapports du service
# --------------------------------------------------------------------------- #
class ImportEnAttente(Base):
    """Ancien rapport dont le client n'a pas été reconnu : conservé jusqu'à ce qu'on crée le client ou qu'on le
    rattache à un client existant (aucun rattachement automatique à un client par défaut dans un lot)."""
    __tablename__ = "imports_en_attente"
    id: Mapped[int] = mapped_column(primary_key=True)
    fichier: Mapped[str] = mapped_column(String(500))
    nom_fichier: Mapped[str] = mapped_column(String(300))
    extension: Mapped[str] = mapped_column(String(10))
    empreinte: Mapped[str] = mapped_column(String(64), unique=True)
    texte: Mapped[str] = mapped_column(Text, default="")
    nom_detecte: Mapped[str | None] = mapped_column(String(200))
    # Motif de l'attente : « client » (client non reconnu) ou « doublon » (ressemble à une intervention existante)
    motif: Mapped[str] = mapped_column(String(20), default="client", server_default="client")
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    doublon_id: Mapped[int | None] = mapped_column(ForeignKey("interventions.id", ondelete="SET NULL"))
    similarite: Mapped[float | None] = mapped_column(Float)
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    client = relationship("Client")
    doublon = relationship("Intervention")


STATUTS_ASSISTANCE = {"a_planifier": "À planifier", "planifiee": "Planifiée", "realisee": "Réalisée", "reportee": "Reportée"}


class AssistancePlanifiee(Base):
    """Assistance mensuelle due à un client pour un mois donné (créée automatiquement chaque mois)."""
    __tablename__ = "assistances_planifiees"
    __table_args__ = (UniqueConstraint("client_id", "annee", "mois"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    annee: Mapped[int] = mapped_column(Integer)
    mois: Mapped[int] = mapped_column(Integer)
    statut: Mapped[str] = mapped_column(String(20), default="a_planifier")
    date_prevue: Mapped[date | None] = mapped_column(Date)
    technicien_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"))
    intervention_id: Mapped[int | None] = mapped_column(ForeignKey("interventions.id", ondelete="SET NULL"))
    justification: Mapped[str] = mapped_column(Text, default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    client = relationship("Client")
    technicien = relationship("Utilisateur")
    intervention = relationship("Intervention")


STATUTS_FORMATION = ("Prévue", "En cours", "Terminée")


class Formation(Base):
    """Parcours d'un technicien : formations suivies ou prévues."""
    __tablename__ = "formations"
    id: Mapped[int] = mapped_column(primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateurs.id", ondelete="CASCADE"), index=True)
    intitule: Mapped[str] = mapped_column(String(300))
    organisme: Mapped[str] = mapped_column(String(200), default="")
    debut: Mapped[date | None] = mapped_column(Date)
    fin: Mapped[date | None] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default="Terminée")
    heures: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    utilisateur = relationship("Utilisateur")


class Certification(Base):
    """Certification obtenue par un technicien, avec son justificatif (PDF ou image)."""
    __tablename__ = "certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateurs.id", ondelete="CASCADE"), index=True)
    intitule: Mapped[str] = mapped_column(String(300))
    editeur: Mapped[str] = mapped_column(String(100), default="Kaspersky")
    numero: Mapped[str] = mapped_column(String(100), default="")
    obtenue_le: Mapped[date] = mapped_column(Date)
    expire_le: Mapped[date | None] = mapped_column(Date, index=True)
    fichier: Mapped[str | None] = mapped_column(String(500))
    nom_fichier: Mapped[str | None] = mapped_column(String(300))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    utilisateur = relationship("Utilisateur")


TYPES_ACTIVITE = {"projet": "Projet interne", "webinaire": "Webinaire / événement", "reunion": "Réunion",
                  "formation_donnee": "Formation dispensée", "veille": "Veille technique", "autre": "Autre"}


class ActiviteInterne(Base):
    """Activité du service sans client : projets internes, webinaires, réunions, veille…"""
    __tablename__ = "activites_internes"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(30), default="projet")
    titre: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    participants: Mapped[list] = mapped_column(JSONB, default=list)
    duree_heures: Mapped[float | None] = mapped_column(Float)
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


PERIODICITES_SERVICE = {"mensuel": 1, "trimestriel": 3, "semestriel": 6, "annuel": 12}


class RapportService(Base):
    """Rapport d'activité du service technique pour une période (versionné, figé à la validation)."""
    __tablename__ = "rapports_service"
    __table_args__ = (UniqueConstraint("periodicite", "annee", "numero", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    periodicite: Mapped[str] = mapped_column(String(20))
    annee: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)  # mois, trimestre ou semestre (1 pour l'année)
    debut: Mapped[date] = mapped_column(Date)
    fin: Mapped[date] = mapped_column(Date)  # exclue
    version: Mapped[int] = mapped_column(Integer, default=1)
    statut: Mapped[str] = mapped_column(String(20), default=BROUILLON)
    donnees: Mapped[dict] = mapped_column(JSONB)
    contenu: Mapped[dict] = mapped_column(JSONB)
    pdf: Mapped[str | None] = mapped_column(String(500))
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"))
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valide_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id", ondelete="SET NULL"))
    valide_le: Mapped[datetime | None] = mapped_column(DateTime)
    cree_par = relationship("Utilisateur", foreign_keys=[cree_par_id])
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])


def journaliser(db, utilisateur, action, detail="", acteur=None):
    """Ajoute une ligne chaînée au journal (dans la transaction en cours)."""
    from .integrite import chainer
    ligne = Journal(utilisateur_id=utilisateur.id if utilisateur else None,
                    acteur=acteur or (utilisateur.email if utilisateur else "système"),
                    action=action, detail=detail or "", quand=datetime.now())
    db.add(ligne)
    chainer(db, ligne)
    return ligne
