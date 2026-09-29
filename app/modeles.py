"""Modèle de données."""
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func)
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
    cree_le: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

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
    """Traçabilité : qui a fait quoi."""
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateurs.id"))
    action: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text, default="")
    quand: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    utilisateur = relationship("Utilisateur")


def journaliser(db, utilisateur, action, detail=""):
    db.add(Journal(utilisateur_id=utilisateur.id if utilisateur else None, action=action, detail=detail))
