# VERSION_UI_2026_08_27_V70_CLEAR_LEFT_NAV_HIERARCHY
import re
import base64
import json
import math
import tempfile
import random
import textwrap
import secrets
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import qrcode
from PIL import Image, ImageChops

import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from upstash_redis import Redis

from levels import LEVELS, LEVEL_NAMES, MOLECULE_LEVEL_NAMES, ELECTRICITY_LEVEL_NAMES, GLASSWARE_LEVEL_NAMES, ION_LEVEL_NAMES


# ============================================================
# CONFIGURATION
# ============================================================

# Version navigation optimisée v2 : callbacks aussi sur tous les retours et déconnexions
st.set_page_config(
    page_title="Ludothèque Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)


# Utiliser toute la hauteur de la fenêtre : le bandeau Streamlit supérieur
# est masqué et le contenu remonte. Les commandes Streamlit restent accessibles
# via le menu de l'application si l'hébergement les expose.
st.markdown(
    """
    <style>
    /* Récupère l'espace du bandeau blanc Streamlit */
    [data-testid="stHeader"] {
        height: 0 !important;
        min-height: 0 !important;
        background: transparent !important;
    }

    [data-testid="stHeader"] > div {
        display: none !important;
    }

    [data-testid="stToolbar"] {
        display: none !important;
    }

    [data-testid="stDecoration"] {
        display: none !important;
    }

    /* Réduit fortement la marge haute native de Streamlit */
    .stMainBlockContainer,
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 0.55rem !important;
    }

    /* Sur mobile, on garde juste un peu d'air en haut */
    @media (max-width: 768px) {
        .stMainBlockContainer,
        [data-testid="stMainBlockContainer"],
        .block-container {
            padding-top: 0.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


ASSETS = Path("assets/molecules")
ASSETS_ELECTRICITY = Path("assets/electricity")
ASSETS_GLASSWARE = Path("assets/glassware")

redis = Redis(
    url=st.secrets["UPSTASH_REDIS_REST_URL"],
    token=st.secrets["UPSTASH_REDIS_REST_TOKEN"],
)

def teacher_key(kind, teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        raise RuntimeError("Aucun professeur connecté.")
    return f"ludo:teacher:{teacher_id}:{kind}"

def get_teacher_accounts():
    try:
        teachers = st.secrets["teachers"]
    except Exception:
        return {}
    accounts = {}
    for teacher_id in teachers:
        data = teachers[teacher_id]
        password = str(data.get("password", ""))
        if password:
            accounts[str(teacher_id)] = {
                "name": str(data.get("name", teacher_id)),
                "password": password,
            }
    return accounts

def current_teacher_name():
    return st.session_state.get("teacher_name", "Professeur")


def content_pilot_enabled_for_teacher(teacher_id=None, teacher_name=None):
    """
    Active l'espace professeur complet pour Christophe et Virginie.

    Les données restent séparées dans Upstash grâce aux clés :
        ludo:teacher:<teacher_id>:...

    Important :
    - Christophe et Virginie disposent de la même interface ;
    - chacun ne lit et n'écrit que ses propres classes, élèves, contenus,
      préparations, défis, résultats et journaux d'activité ;
    - Thierry n'est pas encore activé ici, conformément au déploiement progressif.
    """
    resolved_id = str(
        teacher_id or st.session_state.get("teacher_id", "")
    ).strip()

    resolved_name = str(
        teacher_name or st.session_state.get("teacher_name", "")
    ).strip()

    # Lorsqu'un élève est connecté, on connaît surtout le teacher_id.
    # On retrouve donc le nom du professeur dans les comptes configurés.
    if resolved_id and not resolved_name:
        account = get_teacher_accounts().get(resolved_id, {})
        resolved_name = str(account.get("name", ""))

    identity = f"{resolved_id} {resolved_name}".strip().lower()

    return (
        "christophe" in identity
        or "declerck" in identity
        or "virginie" in identity
    )


PILOT_CONTENTS = {
    "exercise1_states_water": {
        "label": "Exercice 1 — Identifier les états de l’eau",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 5,
        "description": "Choisir, pour chaque situation, le ou les états physiques de l’eau correspondants.",
        "resource_ready": True,
    },
    "exercise2_water_properties": {
        "label": "Exercice 2 — Les particularités des états de l’eau",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 7,
        "description": "Associer des étiquettes à trois représentations de l’eau en utilisant les lettres A, B et C.",
        "resource_ready": True,
    },
    "exercise3_particle_models": {
        "label": "Exercice 3 — Comprendre la modélisation",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 9,
        "description": "Identifier l’état de la matière à partir de la disposition des molécules.",
        "resource_ready": True,
    },
    "exercise4_oxygen_bottle": {
        "label": "Exercice 4 — Propriétés et bouteille de dioxygène",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 11,
        "description": "Relier propriétés moléculaires, état physique et modélisation d’une bouteille de dioxygène.",
        "resource_ready": True,
    },
    "exercise5_seawater_mixture": {
        "label": "Exercice 5 — Modéliser un mélange : l’eau de mer",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 13,
        "description": "Différencier un corps pur et un mélange à l’échelle microscopique.",
        "resource_ready": True,
    },
    "exercise6_water_alcohol_volume": {
        "label": "Exercice 6 — Le mystère du volume perdu : eau + alcool",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 15,
        "description": "Raisonner sur l’organisation des molécules et la conservation de la masse lors d’un mélange.",
        "resource_ready": True,
    },
    "exercise7_solid_mixtures_alloys": {
        "label": "Exercice 7 — Les mélanges solides : les alliages",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 17,
        "description": "Comprendre ce qu’est un alliage et distinguer insertion et substitution à l’échelle microscopique.",
        "resource_ready": True,
    },
    "exercise8_element_symbols": {
        "label": "Exercice 8 — Symboles des éléments",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 30,
        "description": "Utiliser le tableau périodique pour associer noms et symboles des éléments chimiques.",
        "resource_ready": True,
    },
    "exercise9_atom_or_molecule": {
        "label": "Exercice 9 — Atome ou molécule ?",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 32,
        "description": "Distinguer un symbole d’élément d’une formule moléculaire, notamment CO et Co.",
        "resource_ready": True,
    },
    "exercise10_ethanol": {
        "label": "Exercice 10 — Éthanol",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 34,
        "description": "Lire un modèle moléculaire, déterminer sa composition et écrire la formule de l’éthanol.",
        "resource_ready": True,
    },
    "exercise11_nitrous_oxide": {
        "label": "Exercice 11 — Protoxyde d’azote",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 36,
        "description": "Réinvestir symbole, formule, modèle moléculaire et composition autour de l’azote.",
        "resource_ready": True,
    },
    "exercise12_caffeine": {
        "label": "Exercice 12 — Caféine",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 38,
        "description": "Lire une formule chimique et en déduire la composition et le nombre total d’atomes.",
        "resource_ready": True,
    },
    "exercise13_names_formulas": {
        "label": "Exercice 13 — Noms et formules",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 40,
        "description": "Associer un modèle moléculaire à son nom et à sa formule.",
        "resource_ready": True,
    },
    "exercise14_molecule_formulas": {
        "label": "Exercice 14 — Formules de molécules",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 42,
        "description": "Déduire la formule d’une molécule à partir de son modèle.",
        "resource_ready": True,
    },
    "exercise_states_matter": {
        "label": "Entraînement — États de la matière",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 10,
        "description": "Entraînement autocorrigé sur les solides, liquides, gaz et le modèle particulaire.",
        "resource_ready": True,
    },
    "domino_molecules": {
        "label": "Domino Molécules",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 20,
        "description": "Formules, modèles moléculaires et descriptions selon les niveaux déjà créés.",
        "resource_ready": True,
    },
    # Ces trois ressources sont terminées mais ne sont pas rattachées au Thème 1
    # tant que la progression correspondante n'a pas été intégrée.
    "domino_glassware": {
        "label": "Domino Verrerie",
        "chapter": "Autres contenus déjà prêts",
        "order": 10,
        "description": "Reconnaître le matériel de laboratoire à partir de son illustration.",
        "resource_ready": True,
    },
    "domino_ions": {
        "label": "Domino Ions",
        "chapter": "Autres contenus déjà prêts",
        "order": 20,
        "description": "Associer formules, noms et représentations des ions selon les niveaux déjà créés.",
        "resource_ready": True,
    },
    "domino_electricity": {
        "label": "Domino Électricité",
        "chapter": "Autres contenus déjà prêts",
        "order": 30,
        "description": "Passer du montage électrique au schéma normalisé et réciproquement.",
        "resource_ready": True,
    },
}

PROGRESSION_CHAPTERS = [
    "Chapitre 1 — Organisation de la matière",
    "Chapitre 2 — L’air qui nous entoure",
    "Chapitre 3 — Les transformations chimiques",
    "Chapitre 4 — D’autres transformations chimiques",
    "Autres contenus déjà prêts",
]


RESOURCE_BY_THEME = {
    "Molécules": "domino_molecules",
    "Verrerie": "domino_glassware",
    "Ions": "domino_ions",
    "Électricité": "domino_electricity",
}


def get_content_access(teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        return {}
    return redis_read_json(teacher_key("content_access", teacher_id), {})


def save_content_access(access, teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        raise RuntimeError("Aucun professeur associé aux contenus.")
    redis_write_json(teacher_key("content_access", teacher_id), access)


def content_is_open_for_class(content_id, class_name, teacher_id):
    access = get_content_access(teacher_id)
    return bool(access.get(str(class_name), {}).get(content_id, False))


def clear_teacher_session():
    for key in [
        "teacher_authenticated",
        "teacher_id",
        "teacher_name",
        "teacher_section",
        "teacher_password",
        "teacher_account_select",
    ]:
        st.session_state.pop(key, None)


def clear_app_session():
    """Déconnecte complètement l'utilisateur courant de la Ludothèque."""
    clear_teacher_session()

    for key in [
        "app_authenticated",
        "app_user_type",
        "app_student",
        "challenge_student",
        "active_challenge",
        "collab_team_code",
        "entry_student_code",
        "entry_user_type",
        "entry_teacher_password",
        "entry_teacher_account",
    ]:
        st.session_state.pop(key, None)

    st.session_state.page = "home"
    st.query_params.clear()


def current_app_user_label():
    if st.session_state.get("app_user_type") == "student":
        student = st.session_state.get("app_student") or {}
        if student:
            return (
                f"{student.get('first_name', '')} {student.get('last_initial', '')}. "
                f"— {student.get('class_name', '')}"
            ).strip()
        return "Élève"

    if st.session_state.get("app_user_type") == "teacher":
        return current_teacher_name()

    return ""

APP_PUBLIC_URL = st.secrets.get(
    "APP_PUBLIC_URL",
    "https://ludo-physique-chimie.streamlit.app",
).rstrip("/")


# ============================================================
# STYLE MODERNE
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #f8fbff 0%, #ffffff 45%);
    }

    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    h1, h2, h3 {
        letter-spacing: -0.02em;
    }

    div[data-testid="stButton"] > button {
        border-radius: 14px;
        min-height: 3rem;
        font-weight: 700;
        border: 1px solid #d9e3f2;
        box-shadow: 0 4px 12px rgba(31, 55, 90, 0.06);
        transition: all 0.18s ease;
    }

    div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 7px 18px rgba(31, 55, 90, 0.11);
    }

    div[data-testid="stButton"] > button[kind="primary"] {
        background: #22a447;
        color: white;
        border-color: #22a447;
    }

    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: #198b3b;
        border-color: #198b3b;
        color: white;
    }

    div[data-testid="stDownloadButton"] > button[kind="primary"] {
        background: #2f6fe4;
        color: white;
        border-color: #2f6fe4;
        font-weight: 700;
    }

    div[data-testid="stDownloadButton"] > button[kind="primary"]:hover {
        background: #245fc8;
        border-color: #245fc8;
        color: white;
    }

        

    

    

    

    

    

    

    @media (max-width: 900px) {
        

        

        

        
    }

    .section-title {
        text-align: center;
        font-size: 1.65rem;
        font-weight: 800;
        margin: 0.5rem 0 1.1rem 0;
        color: #15284a;
    }

    .nav-card {
        background: white;
        border: 1px solid #e0e8f4;
        border-radius: 22px;
        padding: 1.25rem 1.15rem 1rem 1.15rem;
        min-height: 255px;
        text-align: center;
        box-shadow: 0 8px 24px rgba(31, 55, 90, 0.07);
        margin-bottom: 0.55rem;
    }

    .nav-icon {
        font-size: 3.4rem;
        line-height: 1;
        margin-bottom: 0.75rem;
    }

    .nav-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #153160;
        margin-bottom: 0.55rem;
    }

    .nav-text {
        color: #52647d;
        font-size: 0.96rem;
        line-height: 1.45;
        min-height: 72px;
    }

    .card-blue { border-top: 5px solid #2f6fe4; }
    .card-green { border-top: 5px solid #25a55a; }
    .card-purple { border-top: 5px solid #8f52c7; }
    .card-orange { border-top: 5px solid #f08a24; }
    .card-pink { border-top: 5px solid #cf4a92; }
    .card-cyan { border-top: 5px solid #2ba7b8; }

    .teacher-band {
        background: linear-gradient(135deg, #102a56 0%, #183866 100%);
        color: white;
        border-radius: 18px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }

    .teacher-band-title {
        font-weight: 800;
        font-size: 1.35rem;
    }

    .breadcrumb {
        color: #69809e;
        font-size: 0.92rem;
        margin-bottom: 0.65rem;
    }

    .coming-soon {
        display: inline-block;
        padding: 0.2rem 0.55rem;
        background: #eef3f9;
        color: #71829a;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-top: 0.45rem;
    }

    .stat-card {
        background: white;
        border: 1px solid #e1e8f2;
        border-radius: 18px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 6px 18px rgba(31, 55, 90, 0.05);
    }


    /* ============================================================
       EXERCICE 1 — TABLEAU MODERNE DES ÉTATS DE L'EAU
       ============================================================ */
    .ex1-instruction {
        background: linear-gradient(180deg, #f8fbff 0%, #f3f8ff 100%);
        border: 1px solid #cfe0fb;
        border-radius: 16px;
        padding: 0.9rem 1.1rem;
        color: #324a68;
        margin: 0.4rem 0 1rem 0;
        box-shadow: 0 4px 14px rgba(31, 55, 90, 0.04);
    }

    .ex1-header-cell {
        background: linear-gradient(180deg, #f6f9fd 0%, #eef4fb 100%);
        border-top: 1px solid #dce5f1;
        border-bottom: 1px solid #dce5f1;
        min-height: 52px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        color: #16335f;
        font-size: 1rem;
    }

    .ex1-header-left {
        justify-content: flex-start;
        padding-left: 1rem;
        border-left: 1px solid #dce5f1;
        border-top-left-radius: 14px;
    }

    .ex1-header-right {
        border-right: 1px solid #dce5f1;
        border-top-right-radius: 14px;
    }

    .ex1-row-label {
        min-height: 58px;
        display: flex;
        align-items: center;
        padding: 0.3rem 1rem;
        border-left: 1px solid #e3e9f2;
        border-bottom: 1px solid #dfe6ef;
        color: #162b4d;
        font-weight: 750;
        font-size: 0.98rem;
    }

    .ex1-row-white,
    .ex1-row-gray {
        background: #f1f3f6;
    }

    /* Chaque ligne checkbox adopte le même fond alterné */
    .ex1-check-wrap {
        min-height: 58px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-bottom: 1px solid #dfe6ef;
    }

    .ex1-check-white,
    .ex1-check-gray {
        background: #f1f3f6;
    }

    /* Cases à cocher plus grandes et bien contrastées */
    div[data-testid="stCheckbox"] {
        min-height: 58px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 !important;
        padding: 0 !important;
    }

    div[data-testid="stCheckbox"] label {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
        min-height: 58px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    div[data-testid="stCheckbox"] span[data-baseweb="checkbox"] {
        transform: scale(1.48);
        transform-origin: center center;
    }

    div[data-testid="stCheckbox"] span[data-baseweb="checkbox"] > div {
        width: 24px !important;
        height: 24px !important;
        border: 2px solid #0f9fb3 !important;
        border-radius: 6px !important;
        background: #bfeff4 !important;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,.35);
    }

    div[data-testid="stCheckbox"] input:checked + div {
        background: #10a9bd !important;
        border-color: #087f91 !important;
    }

    div[data-testid="stCheckbox"] svg {
        width: 22px !important;
        height: 22px !important;
        color: white !important;
        stroke-width: 3 !important;
    }

    div[data-testid="stCheckbox"] label:hover span[data-baseweb="checkbox"] > div {
        border-color: #087f91 !important;
        background: #a9e8ef !important;
    }


    /* Correctif renforcé pour les versions récentes de Streamlit/BaseWeb :
       cible directement le carré visuel du checkbox, quel que soit le wrapper. */
    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-child,
    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-child,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-child {
        width: 30px !important;
        height: 30px !important;
        min-width: 30px !important;
        min-height: 30px !important;
        border-radius: 7px !important;
        border: 3px solid #087f91 !important;
        background-color: #66dbe7 !important;
        box-sizing: border-box !important;
        opacity: 1 !important;
        box-shadow:
            0 0 0 2px rgba(8,127,145,.08),
            inset 0 0 0 1px rgba(255,255,255,.35) !important;
    }

    /* État coché : turquoise foncé, coche blanche très visible. */
    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked ~ div:first-of-type,
    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] input:checked ~ span:first-of-type,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] input:checked ~ div:first-of-type,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] input:checked ~ span:first-of-type {
        background-color: #007f92 !important;
        border-color: #005d6c !important;
    }

    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"] svg,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] svg {
        width: 24px !important;
        height: 24px !important;
        color: #ffffff !important;
        fill: #ffffff !important;
        stroke: #ffffff !important;
        stroke-width: 3.2 !important;
        opacity: 1 !important;
    }

    /* Au survol, le carré devient encore un peu plus soutenu. */
    div[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:hover > div:first-child,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:hover > div:first-child {
        background-color: #4bcbd8 !important;
        border-color: #006f80 !important;
    }

    .ex1-tip {
        background: #fff9eb;
        border: 1px solid #f5dda4;
        border-radius: 12px;
        padding: 0.75rem 0.9rem;
        color: #72551a;
        font-weight: 600;
    }

    .ex1-feedback-hint {
        background: #fff7e6;
        border: 1px solid #f4d69b;
        border-radius: 12px;
        padding: .65rem .8rem;
        margin: .25rem 0 .7rem 0;
        color: #73541c;
    }

    .ex1-feedback-correction {
        background: #fff1f1;
        border: 1px solid #f0c8c8;
        border-radius: 12px;
        padding: .65rem .8rem;
        margin: .25rem 0 .7rem 0;
        color: #7b2c2c;
    }

    .ex1-feedback-ok {
        background: #eefaf2;
        border: 1px solid #cdebd6;
        border-radius: 12px;
        padding: .6rem .8rem;
        margin: .25rem 0 .7rem 0;
        color: #24623a;
    }

    .footer-note {
        background: #eef6ff;
        border: 1px solid #d9eafa;
        border-radius: 14px;
        padding: 0.75rem 1rem;
        color: #45617f;
        text-align: center;
        margin-top: 0.15rem;
    }


    /* ============================================================
       ESPACE PROFESSEUR — BANDEAU GAUCHE VISIBLE
       Ce panneau fait partie de la mise en page principale.
       Il ne dépend PAS de la sidebar native Streamlit.
       ============================================================ */

    .st-key-teacher_nav_panel {
        background:
            radial-gradient(circle at 50% 94%, rgba(62, 106, 255, .22), transparent 35%),
            linear-gradient(180deg, #083e7e 0%, #06336b 52%, #042858 100%);
        border-radius: 16px;
        min-height: calc(100vh - .5rem);
        padding: .8rem .68rem 1rem .68rem;
        box-shadow: 0 12px 28px rgba(18, 48, 93, .16);
        border: 1px solid rgba(255,255,255,.08);
        position: sticky;
        top: .65rem;
    }

    .st-key-teacher_nav_panel * {
        color: #f6f9ff;
    }

    .teacher-left-logo {
        padding: .5rem .45rem 1rem .45rem;
        margin-bottom: .5rem;
        border-bottom: 1px solid rgba(255,255,255,.12);
    }

    .teacher-left-logo-title {
        color: #ffffff;
        font-size: 1.02rem;
        line-height: 1.18;
        font-weight: 900;
        letter-spacing: -.02em;
    }

    .teacher-left-logo-sub {
        margin-top: .3rem;
        color: #bdd2ef;
        font-size: .74rem;
        font-weight: 650;
    }

    .teacher-left-section {
        margin: .85rem .55rem .32rem .55rem;
        color: #91b4df !important;
        font-size: .64rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .12em;
    }

    .teacher-left-primary-active {
        display: flex;
        align-items: center;
        min-height: 2.75rem;
        padding: .68rem .78rem;
        margin: .18rem 0;
        border-radius: 11px;
        color: #ffffff !important;
        font-size: .96rem;
        font-weight: 800;
        letter-spacing: -.01em;
        background: linear-gradient(135deg, #315dff 0%, #4b72ff 100%);
        box-shadow: 0 7px 17px rgba(19, 63, 196, .28);
    }

    .st-key-teacher_nav_panel div[data-testid="stButton"] > button {
        width: 100%;
        min-height: 2.45rem !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: .7rem !important;
        padding-right: .55rem !important;
        border-radius: 11px !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        color: #edf5ff !important;
        box-shadow: none !important;
        font-size: .80rem !important;
        font-weight: 720 !important;
    }

    /* Streamlit centre parfois le contenu interne du bouton :
       on force aussi son wrapper et son texte à gauche. */
    .st-key-teacher_nav_panel div[data-testid="stButton"] > button > div,
    .st-key-teacher_nav_panel div[data-testid="stButton"] > button p,
    .st-key-teacher_nav_panel div[data-testid="stButton"] > button span {
        width: 100% !important;
        text-align: left !important;
        justify-content: flex-start !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }

    .teacher-left-primary-active,
    .teacher-left-subactive {
        justify-content: flex-start !important;
        text-align: left !important;
    }

    .st-key-teacher_nav_panel div[data-testid="stButton"] > button:hover {
        transform: none !important;
        background: rgba(86, 123, 255, .22) !important;
        border-color: rgba(181, 205, 255, .16) !important;
    }

    /* Entraînement, Défi et Espace professeur :
       même niveau d'importance, texte plus grand et plus affirmé. */
    .st-key-teacher_primary_training div[data-testid="stButton"] > button,
    .st-key-teacher_primary_challenge div[data-testid="stButton"] > button,
    .st-key-teacher_primary_prof div[data-testid="stButton"] > button {
        min-height: 2.75rem !important;
        padding-left: .78rem !important;
        padding-right: .55rem !important;
        justify-content: flex-start !important;
        text-align: left !important;
        font-size: .96rem !important;
        font-weight: 800 !important;
        letter-spacing: -.01em !important;
        color: #ffffff !important;
    }

    /* Sous-rubriques : retrait visuel uniquement, sans icône ni flèche. */
    .teacher-left-tree {
        margin: .10rem 0 .20rem 0;
        padding: 0;
        border: 0;
        height: 0;
    }

    /* Les sous-rubriques sont volontairement plus petites et décalées.
       Le retrait suffit à montrer qu'elles appartiennent à Espace professeur. */
    .st-key-teacher_sub_classes_students,
    .st-key-teacher_sub_contents,
    .st-key-teacher_sub_tracking,
    .st-key-teacher_sub_challenges,
    .st-key-teacher_sub_results {
        margin-left: 1.15rem !important;
        width: calc(100% - 1.15rem) !important;
        position: relative;
    }

    .st-key-teacher_sub_classes_students::before,
    .st-key-teacher_sub_contents::before,
    .st-key-teacher_sub_tracking::before,
    .st-key-teacher_sub_challenges::before,
    .st-key-teacher_sub_results::before {
        content: "";
        position: absolute;
        left: -.62rem;
        top: .42rem;
        bottom: .42rem;
        width: 2px;
        border-radius: 999px;
        background: rgba(183, 207, 241, .22);
    }

    .st-key-teacher_sub_classes_students div[data-testid="stButton"] > button,
    .st-key-teacher_sub_contents div[data-testid="stButton"] > button,
    .st-key-teacher_sub_tracking div[data-testid="stButton"] > button,
    .st-key-teacher_sub_challenges div[data-testid="stButton"] > button,
    .st-key-teacher_sub_results div[data-testid="stButton"] > button {
        min-height: 2.08rem !important;
        padding-left: .42rem !important;
        padding-right: .35rem !important;
        justify-content: flex-start !important;
        text-align: left !important;
        font-size: .76rem !important;
        font-weight: 600 !important;
        color: #dce9fb !important;
        border-radius: 8px !important;
    }

    .teacher-left-separator {
        height: 1px;
        background: rgba(255,255,255,.18);
        margin: .85rem .35rem .7rem .35rem;
    }

    .teacher-left-subactive {
        display: flex;
        align-items: center;
        min-height: 2.08rem;
        padding: .46rem .48rem;
        margin: .10rem 0 .10rem 1.15rem;
        width: calc(100% - 1.15rem);
        border-radius: 8px;
        background: rgba(72,112,255,.25);
        color: #ffffff !important;
        font-size: .76rem;
        font-weight: 720;
        position: relative;
    }

    .teacher-left-subactive::before {
        content: "";
        position: absolute;
        left: -.62rem;
        top: .42rem;
        bottom: .42rem;
        width: 2px;
        border-radius: 999px;
        background: rgba(183,207,241,.30);
    }

    /* Remonte tout l'espace professeur pour récupérer le blanc inutile en haut. */
    .st-key-teacher_page_shell {
        margin-top: -3.4rem !important;
        padding-top: 0 !important;
    }

    .st-key-teacher_page_shell > div {
        padding-top: 0 !important;
        margin-top: 0 !important;
    }

    .teacher-left-account {
        margin-top: 1rem;
        padding: .72rem .55rem .15rem .55rem;
        border-top: 1px solid rgba(255,255,255,.11);
        color: #bcd0ec !important;
        font-size: .73rem;
        line-height: 1.4;
    }

    /* La colonne de navigation garde une largeur raisonnable. */
    @media (max-width: 950px) {
        .st-key-teacher_nav_panel {
            min-height: auto;
            position: relative;
            top: 0;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# OUTILS D'INTERFACE
# ============================================================

def hero():
    hero_html = (
        '<div style="width:100%;display:flex;justify-content:center;align-items:center;'
        'box-sizing:border-box;padding:18px 40px 8px 40px;">'
        '<div style="width:820px;max-width:calc(100vw - 120px);box-sizing:border-box;'
        'background:linear-gradient(135deg,#102a56 0%,#1f447d 100%);color:white;'
        'border-radius:30px;padding:24px 34px 26px 34px;'
        'box-shadow:0 12px 30px rgba(16,42,86,0.18);text-align:center;overflow:hidden;">'
        '<div style="display:flex;align-items:center;justify-content:center;gap:18px;flex-wrap:wrap;">'
        '<div style="font-size:52px;line-height:1;flex:0 0 auto;">🧪</div>'
        '<div style="text-align:center;flex:0 1 auto;">'
        '<div style="font-size:36px;font-weight:800;line-height:1.08;margin:0;">'
        'Ludothèque Physique-Chimie'
        '</div>'
        '<div style="font-size:17px;margin-top:8px;opacity:0.93;">'
        'Apprendre en jouant, progresser avec plaisir !'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(hero_html, unsafe_allow_html=True)


def nav_card(icon, title, text, color_class="card-blue", coming_soon=False):
    extra = '<div class="coming-soon">À venir</div>' if coming_soon else ""
    st.markdown(
        f"""
        <div class="nav-card {color_class}">
            <div class="nav-icon">{icon}</div>
            <div class="nav-title">{title}</div>
            <div class="nav-text">{text}</div>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


def request_page_transition():
    """Demande l'animation globale lors du prochain rendu de page."""
    st.session_state["_page_transition_pending"] = True


def render_page_transition():
    """Applique une transition douce identique à toutes les navigations.

    Le voile flouté est injecté avant le rendu de la nouvelle page puis disparaît
    automatiquement. Il masque les anciens éléments que Streamlit pourrait laisser
    visibles pendant le rerun.
    """
    if not st.session_state.pop("_page_transition_pending", False):
        return

    st.markdown(
        """
        <style>
        @keyframes ludoPageReveal {
            0% {
                opacity: 1;
                backdrop-filter: blur(14px);
                -webkit-backdrop-filter: blur(14px);
            }
            68% {
                opacity: .92;
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
            }
            100% {
                opacity: 0;
                backdrop-filter: blur(0px);
                -webkit-backdrop-filter: blur(0px);
                visibility: hidden;
            }
        }

        .ludo-page-transition {
            position: fixed;
            inset: 0;
            z-index: 2147483000;
            pointer-events: none;
            background: rgba(248, 251, 255, .76);
            animation: ludoPageReveal .48s cubic-bezier(.22,.61,.36,1) forwards;
        }

        @media (prefers-reduced-motion: reduce) {
            .ludo-page-transition {
                animation-duration: .12s;
            }
        }
        </style>
        <div class="ludo-page-transition" aria-hidden="true"></div>
        """,
        unsafe_allow_html=True,
    )


def go(page):
    """Navigation impérative avec transition globale."""
    request_page_transition()
    st.session_state.page = page
    st.rerun()


def set_page(page):
    """Callback de navigation : même transition pour toutes les pages."""
    request_page_transition()
    st.session_state.page = page


def set_teacher_section(section):
    """Callback de navigation interne à l'espace professeur."""
    request_page_transition()
    st.session_state.teacher_section = section


def logout_app():
    """Déconnexion avec la même transition visuelle que le reste de l'application."""
    request_page_transition()
    clear_app_session()


def back_button(target="home", label="← Retour"):
    """
    Navigation contextuelle.

    - Élève : Retour + Accueil + Déconnexion, toujours au même endroit.
    - Professeur / autre contexte : conserve le simple bouton Retour.
    """
    if st.session_state.get("app_user_type") == "student":
        current_page = str(st.session_state.get("page", "page"))

        back_col, home_col, logout_col, spacer_col = st.columns(
            [1.15, 1.15, 1.35, 6.35],
            gap="small",
        )

        with back_col:
            st.button(
                label,
                key=f"student_nav_back_{current_page}_{target}",
                use_container_width=True,
                on_click=set_page,
                args=(target,),
            )

        with home_col:
            st.button(
                "🏠 Accueil",
                key=f"student_nav_home_{current_page}",
                use_container_width=True,
                on_click=set_page,
                args=("home",),
            )

        with logout_col:
            st.button(
                "Déconnexion",
                key=f"student_nav_logout_{current_page}",
                use_container_width=True,
                on_click=teacher_logout_fast,
            )

        return

    st.button(
        label,
        use_container_width=False,
        on_click=set_page,
        args=(target,),
    )


# ============================================================
# OUTILS UPSTASH
# ============================================================

def redis_read_json(key, default):
    value = redis.get(key)
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def redis_write_json(key, value):
    redis.set(key, json.dumps(value, ensure_ascii=False))


# ============================================================
# COLLABORATION — OUTILS UPSTASH
# ============================================================

def collab_teams_key(teacher_id, challenge_code):
    return f"ludo:teacher:{teacher_id}:challenge:{challenge_code}:teams"


def get_collab_teams(teacher_id, challenge_code):
    return redis_read_json(collab_teams_key(teacher_id, challenge_code), {})


def save_collab_teams(teacher_id, challenge_code, teams):
    redis_write_json(collab_teams_key(teacher_id, challenge_code), teams)


def generate_team_code(teams):
    for _ in range(200):
        code = str(random.randint(100, 999))
        if code not in teams:
            return code
    raise RuntimeError("Impossible de générer un code d'équipe unique.")


def find_student_team(teams, student_id):
    for team_code, team in teams.items():
        if any(m["id"] == student_id for m in team.get("members", [])):
            return team_code, team
    return None, None


def detach_student_from_active_teams(student, challenge):
    """
    Lorsqu'un élève entre à nouveau volontairement dans un défi collaboratif,
    on le retire des anciennes équipes encore actives de ce même défi.

    Les équipes terminées sont conservées intactes comme historique.
    """
    teacher_id = challenge["_teacher_id"]
    challenge_code = str(challenge["code"])
    teams = get_collab_teams(teacher_id, challenge_code)
    changed = False

    for team_code, team in list(teams.items()):
        if team.get("status") in ("finished", "abandoned"):
            continue

        members = team.get("members", [])
        leaving_index = next(
            (
                index
                for index, member in enumerate(members)
                if member["id"] == student["id"]
            ),
            None,
        )

        if leaving_index is None:
            continue

        game = team.get("game")
        old_active_index = None

        if game and members:
            old_active_index = int(game.get("turn_index", 0)) % len(members)

            proposal = game.get("proposal")
            if proposal and proposal.get("student_id") == student["id"]:
                game["proposal"] = None

        members.pop(leaving_index)
        team["members"] = members

        # Ici ce n'est pas un "abandon en cours de jeu" :
        # l'élève démarre volontairement une nouvelle participation.
        # On ne l'ajoute donc pas à la liste "Élèves ayant quitté".
        if not members:
            team["status"] = "abandoned"
            if game:
                game["proposal"] = None
        elif game:
            if old_active_index == leaving_index:
                new_index = leaving_index % len(members)
            elif leaving_index < old_active_index:
                new_index = old_active_index - 1
            else:
                new_index = old_active_index

            game["turn_index"] = new_index % len(members)
            game["proposal"] = None
            team["status"] = "playing"

        teams[team_code] = team
        changed = True

    if changed:
        save_collab_teams(teacher_id, challenge_code, teams)


def init_collab_game(team, challenge):
    order = LEVELS[challenge["level"]]["order"]
    start = random.choice(order)
    remaining = [x for x in order if x != start]
    random.shuffle(remaining)

    team["game"] = {
        "chain": [start],
        "remaining": remaining,
        "errors": 0,
        "error_details": [],
        "started": time.time(),
        "turn_index": 0,
        "proposal": None,
        "finished_at": None,
    }
    team["status"] = "playing"
    return team


def create_collab_team(student, challenge):
    teacher_id = challenge["_teacher_id"]
    challenge_code = str(challenge["code"])

    # Une nouvelle entrée dans le défi = nouvelle constitution volontaire d'équipe.
    detach_student_from_active_teams(student, challenge)
    teams = get_collab_teams(teacher_id, challenge_code)

    code = generate_team_code(teams)
    member = {
        "id": student["id"],
        "first_name": student["first_name"],
        "last_initial": student["last_initial"],
        "class_name": student["class_name"],
        "joined_at": time.time(),
        "turns": 0,
    }

    team = {
        "code": code,
        "challenge_code": challenge_code,
        "teacher_id": teacher_id,
        "class_name": challenge["class_name"],
        "members": [member],
        "target_size": int(challenge.get("team_size", 4)),
        "status": "lobby",
        "created_at": time.time(),
        "game": None,
        "result_saved": False,
    }

    teams[code] = team
    save_collab_teams(teacher_id, challenge_code, teams)
    return code, team, None


def join_collab_team(student, challenge, team_code):
    teacher_id = challenge["_teacher_id"]
    challenge_code = str(challenge["code"])
    team_code = team_code.strip()

    # L'élève choisit explicitement une équipe pour cette nouvelle participation.
    detach_student_from_active_teams(student, challenge)
    teams = get_collab_teams(teacher_id, challenge_code)

    team = teams.get(team_code)
    if not team:
        return None, None, "Code d'équipe inconnu."

    if team.get("status") in ("finished", "abandoned"):
        return None, None, "Cette équipe n'est plus disponible."

    target_size = int(team.get("target_size", 4))

    if len(team.get("members", [])) >= target_size:
        return None, None, "Cette équipe est déjà complète."

    # Si l'élève avait quitté cette équipe auparavant, on retire son départ
    # de la liste active des départs puisqu'il revient dans la partie.
    previous_departures = team.get("departures", [])
    team["departures"] = [
        departure
        for departure in previous_departures
        if departure.get("id") != student["id"]
    ]

    team["members"].append(
        {
            "id": student["id"],
            "first_name": student["first_name"],
            "last_initial": student["last_initial"],
            "class_name": student["class_name"],
            "joined_at": time.time(),
            "turns": 0,
        }
    )

    if team.get("status") == "lobby":
        if len(team["members"]) >= target_size:
            team = init_collab_game(team, challenge)
    elif team.get("status") == "playing":
        # La partie a déjà commencé : le nouvel élève rejoint simplement
        # la rotation existante, sans réinitialiser la chaîne ni le score.
        game = team.get("game")
        if game and len(team["members"]) == 1:
            game["turn_index"] = 0

    teams[team_code] = team
    save_collab_teams(teacher_id, challenge_code, teams)
    return team_code, team, None


def get_collab_team(teacher_id, challenge_code, team_code):
    return get_collab_teams(teacher_id, str(challenge_code)).get(str(team_code))


def save_collab_team(team):
    teams = get_collab_teams(team["teacher_id"], team["challenge_code"])
    teams[str(team["code"])] = team
    save_collab_teams(team["teacher_id"], team["challenge_code"], teams)


def leave_collab_team(student, challenge, team_code):
    """
    Retire proprement un élève d'une équipe collaborative en cours.

    - La partie continue avec tous les élèves restants, même s'il n'en reste qu'un.
    - La rotation est recalée pour ne jamais attendre un élève parti.
    - Le départ est enregistré afin que le professeur puisse le voir.
    - Si l'équipe devient vide, son état est conservé comme équipe abandonnée.
    """
    teacher_id = challenge["_teacher_id"]
    challenge_code = str(challenge["code"])
    team_code = str(team_code)

    teams = get_collab_teams(teacher_id, challenge_code)
    team = teams.get(team_code)

    if not team:
        return

    if team.get("status") == "finished":
        return

    members = team.get("members", [])
    leaving_index = next(
        (
            index
            for index, member in enumerate(members)
            if member["id"] == student["id"]
        ),
        None,
    )

    if leaving_index is None:
        return

    game = team.get("game")
    old_active_index = None

    if game and members:
        old_active_index = int(game.get("turn_index", 0)) % len(members)

        proposal = game.get("proposal")
        if proposal and proposal.get("student_id") == student["id"]:
            game["proposal"] = None

    leaving_member = members[leaving_index]

    team.setdefault("departures", []).append(
        {
            "id": leaving_member["id"],
            "first_name": leaving_member["first_name"],
            "last_initial": leaving_member["last_initial"],
            "left_at": time.time(),
            "left_at_text": datetime.now().isoformat(timespec="seconds"),
            "reason": "quit_button",
        }
    )

    members.pop(leaving_index)
    team["members"] = members

    if not members:
        team["status"] = "abandoned"
        if game:
            game["proposal"] = None
        teams[team_code] = team
        save_collab_teams(teacher_id, challenge_code, teams)
        return

    if game:
        # Si l'élève qui partait avait la main, le joueur suivant
        # prend immédiatement le relais. Cela fonctionne aussi s'il
        # ne reste qu'un seul élève : son index devient 0.
        if old_active_index == leaving_index:
            new_index = leaving_index % len(members)
        elif leaving_index < old_active_index:
            new_index = old_active_index - 1
        else:
            new_index = old_active_index

        game["turn_index"] = new_index % len(members)
        game["proposal"] = None
        team["status"] = "playing"

    teams[team_code] = team
    save_collab_teams(teacher_id, challenge_code, teams)


# ============================================================
# CLASSES
# ============================================================

def get_classes():
    return sorted(set(redis_read_json(teacher_key("classes"), [])))


def add_class(class_name):
    class_name = class_name.strip().upper()
    if not class_name:
        return False

    classes = get_classes()
    if class_name in classes:
        return False

    classes.append(class_name)
    redis_write_json(teacher_key("classes"), sorted(classes))
    return True


# ============================================================
# ÉLÈVES
# ============================================================

def get_students():
    return redis_read_json(teacher_key("students"), [])


def save_students(students):
    redis_write_json(teacher_key("students"), students)


def generate_student_code():
    """Génère un code élève unique de 6 caractères, facile à saisir.

    Les caractères ambigus (0/O, 1/I) sont volontairement exclus.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    existing = set()

    for teacher_id in get_teacher_accounts():
        for student in redis_read_json(teacher_key("students", teacher_id), []):
            code = str(student.get("code", "")).strip().upper()
            if code:
                existing.add(code)

    for _ in range(1000):
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in existing:
            return code

    raise RuntimeError("Impossible de générer un code élève unique.")


def add_student(first_name, last_initial, class_name):
    first_name = first_name.strip()
    last_initial = last_initial.strip().upper().replace(".", "")[:1]

    if not first_name or not last_initial or not class_name:
        return None, "Prénom, initiale et classe sont obligatoires."

    students = get_students()

    student = {
        "id": secrets.token_urlsafe(12),
        "code": generate_student_code(),
        "first_name": first_name,
        "last_initial": last_initial,
        "class_name": class_name,
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    students.append(student)
    save_students(students)

    return student, None


def find_student_by_code(code):
    code = code.strip().upper()
    for teacher_id in get_teacher_accounts():
        for student in redis_read_json(teacher_key("students", teacher_id), []):
            if student.get("active", True) and student["code"] == code:
                found = dict(student)
                found["_teacher_id"] = teacher_id
                return found
    return None


def find_student_by_id(student_id):
    student_id = str(student_id).strip()
    for teacher_id in get_teacher_accounts():
        for student in redis_read_json(teacher_key("students", teacher_id), []):
            if student.get("active", True) and student["id"] == student_id:
                found = dict(student)
                found["_teacher_id"] = teacher_id
                return found
    return None


def normalize_column_name(name):
    return (
        str(name)
        .strip()
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ù", "u")
        .replace("ï", "i")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("ç", "c")
        .replace("_", " ")
        .replace("-", " ")
    )


def detect_student_columns(df):
    normalized = {normalize_column_name(col): col for col in df.columns}

    candidates = {
        "first": ["prenom", "prénom", "first name", "firstname"],
        "initial": [
            "initiale",
            "initiale nom",
            "initiale du nom",
            "initiale nom de famille",
        ],
        "class": ["classe", "class", "division"],
    }

    def find_candidate(values):
        for value in values:
            key = normalize_column_name(value)
            if key in normalized:
                return normalized[key]
        return None

    return (
        find_candidate(candidates["first"]),
        find_candidate(candidates["initial"]),
        find_candidate(candidates["class"]),
    )


def import_students_from_dataframe(df):
    first_col, initial_col, class_col = detect_student_columns(df)

    missing = []

    if not first_col:
        missing.append("Prénom")
    if not initial_col:
        missing.append("Initiale du nom")
    if not class_col:
        missing.append("Classe")

    if missing:
        return 0, 0, [
            "Colonne(s) obligatoire(s) introuvable(s) : "
            + ", ".join(missing)
            + "."
        ]

    students = get_students()

    existing_keys = {
        (
            s["first_name"].strip().lower(),
            s["last_initial"].strip().upper(),
            s["class_name"].strip().upper(),
        )
        for s in students
    }

    added = 0
    duplicates = 0
    errors = []

    for excel_index, row in df.iterrows():
        row_number = excel_index + 2

        first_name = str(row.get(first_col, "")).strip()
        class_name = str(row.get(class_col, "")).strip().upper()
        last_initial = (
            str(row.get(initial_col, ""))
            .strip()
            .upper()
            .replace(".", "")[:1]
        )

        if not first_name and not class_name and not last_initial:
            continue

        if not first_name or not class_name or not last_initial:
            errors.append(
                f"Ligne {row_number} : prénom, initiale du nom ou classe manquant."
            )
            continue

        key = (first_name.lower(), last_initial, class_name)

        if key in existing_keys:
            duplicates += 1
            continue

        add_class(class_name)

        student = {
            "id": secrets.token_urlsafe(12),
            "code": generate_student_code(),
            "first_name": first_name,
            "last_initial": last_initial,
            "class_name": class_name,
            "active": True,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        students.append(student)
        existing_keys.add(key)
        added += 1

    save_students(students)

    return added, duplicates, errors


def make_student_template():
    return pd.DataFrame(
        [
            {"Prénom": "Emma", "Initiale du nom": "D", "Classe": "4B"},
            {"Prénom": "Lucas", "Initiale du nom": "M", "Classe": "4B"},
        ]
    )


def student_template_xlsx_bytes():
    """Génère un véritable fichier Excel .xlsx servant de modèle d'import."""
    buffer = BytesIO()
    template_df = make_student_template()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        template_df.to_excel(
            writer,
            index=False,
            sheet_name="Élèves",
        )

        worksheet = writer.book["Élèves"]
        worksheet.freeze_panes = "A2"
        worksheet.column_dimensions["A"].width = 18
        worksheet.column_dimensions["B"].width = 22
        worksheet.column_dimensions["C"].width = 12

        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
            cell.alignment = cell.alignment.copy(horizontal="center")

    buffer.seek(0)
    return buffer.getvalue()


def delete_student(student_id):
    students = get_students()
    new_students = [s for s in students if s["id"] != student_id]

    if len(new_students) == len(students):
        return False

    save_students(new_students)
    return True


def regenerate_student_code(student_id):
    """Remplace uniquement le code d'accès d'un élève.

    La fiche, la classe et les résultats existants ne sont pas modifiés.
    Le QR personnel étant construit à partir du code, il change lui aussi.
    """
    students = get_students()

    for student in students:
        if student.get("id") == student_id:
            old_code = student.get("code", "")
            new_code = generate_student_code()
            student["code"] = new_code
            student["code_regenerated_at"] = datetime.now().isoformat(timespec="seconds")
            save_students(students)
            return True, old_code, new_code

    return False, None, None


@st.dialog("Régénérer le code personnel")
def regenerate_student_code_dialog(student_id):
    """Confirmation modale : reste visible même pour un élève placé en haut d'une longue liste."""
    students = get_students()
    student = next((s for s in students if s.get("id") == student_id), None)

    if not student:
        st.error("Élève introuvable.")
        if st.button("Fermer", use_container_width=True):
            st.rerun()
        return

    st.markdown(
        f"### {student['first_name']} {student['last_initial']}. — {student['class_name']}"
    )
    st.warning(
        "L'ancien code ne fonctionnera plus et le QR de l'ancienne carte "
        "deviendra lui aussi invalide. La classe et les résultats ne seront pas modifiés."
    )

    confirm_col, cancel_col = st.columns(2)

    with confirm_col:
        if st.button(
            "✅ Confirmer",
            type="primary",
            use_container_width=True,
            key=f"dialog_confirm_regen_{student_id}",
        ):
            ok, old_code, new_code = regenerate_student_code(student_id)
            if ok:
                st.session_state["last_regenerated_student"] = {
                    "id": student["id"],
                    "first_name": student["first_name"],
                    "last_initial": student["last_initial"],
                    "new_code": new_code,
                }
                st.rerun()
            else:
                st.error("Élève introuvable.")

    with cancel_col:
        if st.button(
            "Annuler",
            use_container_width=True,
            key=f"dialog_cancel_regen_{student_id}",
        ):
            st.rerun()


def delete_class(class_name):
    students = get_students()

    if any(s["class_name"] == class_name for s in students):
        return False, "Cette classe contient encore des élèves."

    classes = [c for c in get_classes() if c != class_name]
    redis_write_json(teacher_key("classes"), classes)
    return True, None


def delete_collaborative_team_data():
    """Supprime les données d'équipes liées aux défis du professeur connecté."""
    teacher_id = st.session_state.get("teacher_id")
    challenges = redis_read_json(teacher_key("challenges"), [])

    for challenge in challenges:
        redis.delete(
            collab_teams_key(
                teacher_id,
                challenge["code"],
            )
        )


def reset_challenges():
    """Supprime tous les défis et les équipes collaboratives associées."""
    delete_collaborative_team_data()
    redis_write_json(teacher_key("challenges"), [])


def reset_results():
    """Supprime uniquement les résultats."""
    redis_write_json(teacher_key("results"), [])


def reset_tracking():
    """Supprime le suivi d'entraînement et les préparations d'évaluation."""
    redis_write_json(teacher_key("activity_log"), [])
    redis_write_json(teacher_key("evaluation_preparations"), [])


def reset_students():
    """Supprime uniquement les élèves. Les classes sont conservées."""
    redis_write_json(teacher_key("students"), [])


def reset_classes_and_students():
    """Supprime les classes et les élèves, sans toucher aux défis ni aux résultats."""
    redis_write_json(teacher_key("classes"), [])
    redis_write_json(teacher_key("students"), [])


def reset_database():
    """Réinitialisation complète des données du professeur connecté."""
    delete_collaborative_team_data()
    redis_write_json(teacher_key("classes"), [])
    redis_write_json(teacher_key("students"), [])
    redis_write_json(teacher_key("challenges"), [])
    redis_write_json(teacher_key("results"), [])
    redis_write_json(teacher_key("activity_log"), [])
    redis_write_json(teacher_key("evaluation_preparations"), [])


# ============================================================
# QR ET PDF
# ============================================================

def student_qr_url(student):
    # Le QR contient le code personnel courant. Un nouveau code = un nouveau QR.
    return f"{APP_PUBLIC_URL}/?student_code={student['code']}"


def make_qr_png_bytes(student):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(student_qr_url(student))
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer.getvalue()


def generate_student_cards_pdf(students):
    """Génère 8 cartes par page avec les identifiants cachés sous un volet.

    Le bandeau inférieur contient le QR et le code personnel. Une fois la carte
    découpée, l'élève plie ce bandeau vers le haut : les deux moyens d'accès se
    retrouvent contre la carte et ne sont plus visibles sans soulever le volet.
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    page_width, page_height = A4
    margin_x = 10 * mm
    margin_y = 10 * mm
    gap_x = 6 * mm
    gap_y = 5 * mm

    cols = 2
    rows = 4

    card_width = (page_width - 2 * margin_x - gap_x) / cols
    card_height = (page_height - 2 * margin_y - 3 * gap_y) / rows

    flap_height = 27 * mm
    qr_size = 20 * mm

    sorted_students = sorted(
        students,
        key=lambda s: (
            s["class_name"],
            s["first_name"].lower(),
            s["last_initial"],
        ),
    )

    for index, student in enumerate(sorted_students):
        slot = index % (cols * rows)

        if slot == 0 and index > 0:
            pdf.showPage()

        row = slot // cols
        col = slot % cols

        x = margin_x + col * (card_width + gap_x)
        y = (
            page_height
            - margin_y
            - (row + 1) * card_height
            - row * gap_y
        )

        pdf.setLineWidth(0.8)
        pdf.roundRect(
            x, y, card_width, card_height, 4 * mm, stroke=1, fill=0
        )

        fold_y = y + flap_height

        # Partie fixe de la carte.
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 7.5 * mm,
            "Ludothèque Physique-Chimie",
        )

        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 16 * mm,
            f"{student['first_name']} {student['last_initial']}.",
        )

        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 23 * mm,
            f"Classe : {student['class_name']}",
        )

        pdf.setFont("Helvetica", 6.8)
        pdf.setFillGray(0.35)
        pdf.drawString(
            x + 5 * mm,
            fold_y + 2.8 * mm,
            "Soulève le volet uniquement pour t'identifier.",
        )
        pdf.setFillGray(0)

        # Ligne de pli.
        pdf.saveState()
        pdf.setDash(2.2, 2.2)
        pdf.setLineWidth(0.7)
        pdf.line(x + 3 * mm, fold_y, x + card_width - 3 * mm, fold_y)
        pdf.restoreState()

        pdf.setFont("Helvetica-Bold", 6.8)
        pdf.drawCentredString(
            x + card_width / 2,
            fold_y - 3 * mm,
            "VOLET CONFIDENTIEL — PLIER ICI VERS LE HAUT",
        )

        # Zone confidentielle : code + QR, tous deux cachés lorsque le volet est fermé.
        pdf.setFillGray(0.94)
        pdf.roundRect(
            x + 2.5 * mm,
            y + 2.5 * mm,
            card_width - 5 * mm,
            flap_height - 6 * mm,
            2.5 * mm,
            stroke=0,
            fill=1,
        )
        pdf.setFillGray(0)

        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(
            x + 5 * mm,
            y + flap_height - 9 * mm,
            "Code personnel",
        )

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(
            x + 5 * mm,
            y + 7 * mm,
            student["code"],
        )

        qr_reader = ImageReader(BytesIO(make_qr_png_bytes(student)))
        qr_x = x + card_width - qr_size - 5 * mm
        qr_y = y + 4.5 * mm

        pdf.drawImage(
            qr_reader,
            qr_x,
            qr_y,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )

        pdf.setFont("Helvetica", 5.7)
        pdf.drawCentredString(
            qr_x + qr_size / 2,
            y + 2.8 * mm,
            "QR personnel",
        )

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# DÉFIS
# ============================================================

def get_challenges():
    return expire_current_teacher_challenges()


def save_challenges(challenges):
    redis_write_json(teacher_key("challenges"), challenges)


def generate_challenge_code():
    existing = set()
    for teacher_id in get_teacher_accounts():
        for challenge in redis_read_json(teacher_key("challenges", teacher_id), []):
            existing.add(str(challenge["code"]))
    for _ in range(100):
        code = str(random.randint(1000, 9999))
        if code not in existing:
            return code
    raise RuntimeError("Impossible de générer un code de défi unique.")


def create_challenge(
    class_name,
    activity,
    theme,
    level,
    max_attempts,
    duration_minutes=55,
    no_time_limit=False,
    mode="Individuel",
    team_size=4,
):
    challenges = get_challenges()
    created_ts = time.time()

    if no_time_limit:
        expires_at = None
        stored_duration = None
    else:
        stored_duration = int(duration_minutes)
        expires_at = created_ts + stored_duration * 60

    challenge = {
        "code": generate_challenge_code(),
        "class_name": class_name,
        "activity": activity,
        "theme": theme,
        "game": f"{activity} — {theme}",
        "level": level,
        "max_attempts": int(max_attempts),
        "status": "open",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "created_ts": created_ts,
        "duration_minutes": stored_duration,
        "expires_at": expires_at,
        "mode": mode,
        "team_size": int(team_size) if mode == "Collaboratif" else None,
    }

    challenges.append(challenge)
    save_challenges(challenges)
    return challenge


def challenge_is_expired(challenge):
    expires_at = challenge.get("expires_at")
    if expires_at in (None, ""):
        return False

    try:
        return time.time() >= float(expires_at)
    except (TypeError, ValueError):
        return False


def challenge_remaining_seconds(challenge):
    expires_at = challenge.get("expires_at")
    if expires_at in (None, ""):
        return None

    try:
        return max(0, int(float(expires_at) - time.time()))
    except (TypeError, ValueError):
        return None


def format_remaining_time(seconds):
    if seconds is None:
        return "Sans limite"

    if seconds <= 0:
        return "Terminé"

    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours} h {minutes:02d} min"

    if minutes:
        return f"{minutes} min {sec:02d} s"

    return f"{sec} s"


def expire_current_teacher_challenges():
    """Ferme automatiquement les défis arrivés à échéance."""
    challenges = redis_read_json(teacher_key("challenges"), [])
    changed = False

    for challenge in challenges:
        if (
            challenge.get("status") == "open"
            and challenge_is_expired(challenge)
        ):
            challenge["status"] = "closed"
            challenge["closed_reason"] = "expired"
            changed = True

    if changed:
        redis_write_json(teacher_key("challenges"), challenges)

    return challenges


def close_challenge(code):
    challenges = get_challenges()

    for challenge in challenges:
        if str(challenge["code"]) == str(code):
            challenge["status"] = "closed"

    save_challenges(challenges)


def find_open_challenge(code, teacher_id):
    code = code.strip()
    challenges = redis_read_json(teacher_key("challenges", teacher_id), [])
    changed = False

    for challenge in challenges:
        if challenge.get("status") == "open" and challenge_is_expired(challenge):
            challenge["status"] = "closed"
            challenge["closed_reason"] = "expired"
            changed = True

    if changed:
        redis_write_json(
            teacher_key("challenges", teacher_id),
            challenges,
        )

    for challenge in challenges:
        if (
            str(challenge["code"]) == code
            and challenge.get("status") == "open"
        ):
            found = dict(challenge)
            found["_teacher_id"] = teacher_id
            return found

    return None



# ============================================================
# SUIVI PÉDAGOGIQUE
# ============================================================

def activity_log_key(teacher_id=None):
    return teacher_key("activity_log", teacher_id)


def get_activity_log(teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        return []
    return redis_read_json(activity_log_key(teacher_id), [])


def save_activity_log(rows, teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        raise RuntimeError("Aucun professeur associé au suivi.")
    redis_write_json(activity_log_key(teacher_id), rows)


def register_student_login(student):
    """Enregistre uniquement la dernière connexion utile au suivi pédagogique."""
    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    students = redis_read_json(teacher_key("students", teacher_id), [])
    changed = False
    now = datetime.now().isoformat(timespec="seconds")

    for stored in students:
        if stored.get("id") == student.get("id"):
            stored["last_login_at"] = now
            changed = True
            break

    if changed:
        redis_write_json(teacher_key("students", teacher_id), students)


def record_training_result(
    student,
    resource_id,
    score_percent,
    completed_items,
    total_items,
    errors=0,
):
    """Enregistre une réalisation d'exercice sans transformer l'entraînement en note."""
    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    now = datetime.now().isoformat(timespec="seconds")

    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == resource_id
        and row.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "completed",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": resource_id,
        "resource_label": PILOT_CONTENTS.get(resource_id, {}).get("label", resource_id),
        "chapter": PILOT_CONTENTS.get(resource_id, {}).get("chapter", ""),
        "score_percent": int(score_percent),
        "completed_items": int(completed_items),
        "total_items": int(total_items),
        "errors": int(errors),
        "attempt_number": len(previous) + 1,
        "finished_at": now,
    })
    save_activity_log(rows, teacher_id)


def evaluation_preparations_key(teacher_id=None):
    return teacher_key("evaluation_preparations", teacher_id)


def get_evaluation_preparations(teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        return []
    return redis_read_json(evaluation_preparations_key(teacher_id), [])


def save_evaluation_preparations(preparations, teacher_id=None):
    teacher_id = teacher_id or st.session_state.get("teacher_id")
    if not teacher_id:
        raise RuntimeError("Aucun professeur associé aux préparations.")
    redis_write_json(evaluation_preparations_key(teacher_id), preparations)


def tracked_exercise_ids():
    """Ressources dont la réalisation produit déjà un résultat exploitable."""
    return [
        "exercise1_states_water",
        "exercise2_water_properties",
        "exercise3_particle_models",
        "exercise4_oxygen_bottle",
        "exercise5_seawater_mixture",
        "exercise6_water_alcohol_volume",
        "exercise7_solid_mixtures_alloys",
        "exercise8_element_symbols",
        "exercise9_atom_or_molecule",
        "exercise10_ethanol",
        "exercise11_nitrous_oxide",
        "exercise12_caffeine",
        "exercise13_names_formulas",
        "exercise14_molecule_formulas",
        "exercise_states_matter",
    ]


def latest_training_by_student_resource(rows):
    latest = {}
    for row in rows:
        if row.get("activity_kind") != "training":
            continue
        key = (row.get("student_id"), row.get("resource_id"))
        current = latest.get(key)
        if current is None or str(row.get("finished_at", "")) > str(current.get("finished_at", "")):
            latest[key] = row
    return latest


def training_attempt_counts(rows):
    counts = {}
    restarted = {}
    for row in rows:
        if row.get("activity_kind") != "training":
            continue
        key = (row.get("student_id"), row.get("resource_id"))
        counts[key] = counts.get(key, 0) + 1
        if row.get("status") == "restarted":
            restarted[key] = restarted.get(key, 0) + 1
    return counts, restarted


def format_short_datetime(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


# ============================================================
# RÉSULTATS
# ============================================================

def get_results():
    return redis_read_json(teacher_key("results"), [])


def save_result(student, challenge, errors, elapsed):
    teacher_id = challenge.get("_teacher_id") or student.get("_teacher_id")
    results = redis_read_json(teacher_key("results", teacher_id), [])

    previous = [
        r
        for r in results
        if r.get("student_id") == student["id"]
        and str(r.get("challenge_code", "")) == str(challenge["code"])
    ]

    attempt = len(previous) + 1

    if attempt > int(challenge["max_attempts"]):
        return False, "Nombre maximal de tentatives atteint."

    result = {
        "student_id": student["id"],
        "student_code": student["code"],
        "first_name": student["first_name"],
        "last_initial": student["last_initial"],
        "class_name": student["class_name"],
        "challenge_code": challenge["code"],
        "game": challenge["game"],
        "activity": challenge.get("activity", "Dominos"),
        "theme": challenge.get("theme", "Molécules"),
        "level": challenge["level"],
        "attempt": attempt,
        "errors": int(errors),
        "time_seconds": int(elapsed),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }

    results.append(result)
    redis_write_json(teacher_key("results", teacher_id), results)

    return True, result


def attempts_used(student, challenge):
    teacher_id = challenge.get("_teacher_id") or student.get("_teacher_id")
    results = redis_read_json(teacher_key("results", teacher_id), [])
    return len([
        r for r in results
        if r.get("student_id") == student["id"]
        and str(r.get("challenge_code", "")) == str(challenge["code"])
    ])


def save_collab_result(team, challenge):
    if team.get("result_saved"):
        return False

    teacher_id = team["teacher_id"]
    results = redis_read_json(teacher_key("results", teacher_id), [])
    game = team["game"]
    elapsed = int((game.get("finished_at") or time.time()) - game["started"])

    results.append(
        {
            "result_type": "team",
            "team_code": team["code"],
            "team_members": [
                {
                    "id": m["id"],
                    "first_name": m["first_name"],
                    "last_initial": m["last_initial"],
                    "turns": m.get("turns", 0),
                }
                for m in team["members"]
            ],
            "team_departures": team.get("departures", []),
            "first_name": f"Équipe {team['code']}",
            "last_initial": "",
            "class_name": team["class_name"],
            "challenge_code": challenge["code"],
            "game": challenge["game"],
            "activity": challenge.get("activity", "Dominos"),
            "theme": challenge.get("theme", "Molécules"),
            "level": challenge["level"],
            "attempt": 1,
            "errors": int(game["errors"]),
            "error_details": game.get("error_details", []),
            "time_seconds": elapsed,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    redis_write_json(teacher_key("results", teacher_id), results)
    team["result_saved"] = True
    save_collab_team(team)
    return True


# ============================================================
# MOTEUR DOMINOS
# ============================================================

def game_key(level, suffix="free"):
    return f"game_{suffix}_{level}"


def init_game(level, suffix="free"):
    order = LEVELS[level]["order"]
    start = random.choice(order)
    remaining = [x for x in order if x != start]
    random.shuffle(remaining)

    st.session_state[game_key(level, suffix)] = {
        "chain": [start],
        "remaining": remaining,
        "errors": 0,
        "started": time.time(),
        "saved": False,
    }


def asset_path(image_name):
    """Retourne le chemin d'un asset moléculaire ou électrique."""
    image_name = str(image_name)

    if image_name.endswith(".png"):
        return ASSETS_ELECTRICITY / image_name

    if image_name.startswith("elec_"):
        # Compatibilité avec d'anciennes données encore éventuellement en session.
        return ASSETS_ELECTRICITY / f"{image_name}.png"

    return ASSETS / f"{image_name}.svg"


def formula_block(formula):
    if isinstance(formula, str) and formula.startswith("img:"):
        image_name = formula[4:]
        st.image(str(asset_path(image_name)), width=240)
        return

    st.markdown(
        f"""
        <div style="
            min-height:115px;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:1.55rem;
            text-align:center;
            font-weight:500;
        ">
            {formula}
        </div>
        """,
        unsafe_allow_html=True,
    )



def text_block(text):
    st.markdown(
        f"""
        <div style="
            min-height:115px;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:1.05rem;
            line-height:1.3;
            text-align:center;
            font-weight:500;
            padding:8px 10px;
        ">
            {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def domino_side_block(side):
    """Affiche une moitié de domino enrichi."""
    if isinstance(side, str) and side.startswith("img:"):
        molecule_block(side[4:])
    elif isinstance(side, str) and side.startswith("glass:"):
        glassware_block(side[6:])
    elif isinstance(side, str) and side.startswith("ion:"):
        ion_formula_block(side[4:])
    elif isinstance(side, str) and side.startswith("ionname:"):
        ion_name_block(side[8:])
    elif isinstance(side, str) and side.startswith("formula:"):
        formula_block(side[8:])
    elif isinstance(side, str) and side.startswith("text:"):
        text_block(side[5:])
    else:
        formula_block(str(side))



def _chem_formula_html(raw):
    """Transforme une formule simple (NH4, Cr2O7...) en HTML avec indices."""
    import re
    parts = re.split(r'(\\d+)', str(raw))
    out = []
    for part in parts:
        if part.isdigit():
            out.append(f"<sub>{part}</sub>")
        else:
            out.append(part)
    return "".join(out)


def ion_formula_block(spec):
    """
    spec attendu : 'Na:+1', 'SO4:-2', etc.
    Affiche une formule d'ion au centre, comme sur les cartes papier.
    """
    formula, charge = spec.rsplit(":", 1)
    charge_num = int(charge)
    if charge_num == 0:
        charge_html = ""
    else:
        sign = "+" if charge_num > 0 else "−"
        n = abs(charge_num)
        charge_html = f"<sup>{'' if n == 1 else n}{sign}</sup>"

    formula_html = _chem_formula_html(formula)

    st.markdown(
        f"""
        <div style="
            min-height:118px;
            display:flex;
            align-items:center;
            justify-content:center;
            font-family:Arial,Helvetica,sans-serif;
            font-size:1.65rem;
            font-weight:800;
            color:#111;
            line-height:1;
        ">
            {formula_html}{charge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def ion_name_block(name):
    st.markdown(
        f"""
        <div style="
            min-height:118px;
            display:flex;
            align-items:center;
            justify-content:center;
            text-align:center;
            font-family:Arial,Helvetica,sans-serif;
            font-size:1.22rem;
            font-weight:700;
            color:#111;
            line-height:1.22;
            padding:8px 12px;
        ">
            {name}
        </div>
        """,
        unsafe_allow_html=True,
    )


def ion_domino_html(left_side, right_side, is_available=False):
    def render(side):
        if side.startswith("ion:"):
            spec = side[4:]
            formula, charge = spec.rsplit(":", 1)
            charge_num = int(charge)
            sign = "+" if charge_num > 0 else "−"
            n = abs(charge_num)
            charge_html = f"<sup>{'' if n == 1 else n}{sign}</sup>" if charge_num else ""
            return '<div class="ion-formula">' + _chem_formula_html(formula) + charge_html + '</div>'
        if side.startswith("ionname:"):
            return '<div class="ion-name">' + side[8:] + '</div>'
        return '<div class="ion-name">' + str(side) + '</div>' 
    if is_available:
        bg = "linear-gradient(135deg,#d9ecff,#b8dcfb)"
        border = "#17476d"
    else:
        bg = "linear-gradient(135deg,#fff3b0,#ffd966)"
        border = "#8a6500"

    html = (
        '<style>.ion-domino{display:grid;grid-template-columns:42% 58%;min-height:132px;background:var(--ion-bg);border:4px solid var(--ion-border);border-radius:22px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.08)}.ion-domino>div{display:flex;align-items:center;justify-content:center;padding:10px}.ion-domino>div+div{border-left:3px solid var(--ion-border)}.ion-formula{font-family:Arial,Helvetica,sans-serif;font-size:2.2rem;font-weight:900;line-height:1;color:#111}.ion-formula sub{font-size:.55em;vertical-align:-.25em}.ion-formula sup{font-size:.55em;vertical-align:.72em;margin-left:1px}.ion-name{font-family:Arial,Helvetica,sans-serif;font-size:1.15rem;font-weight:700;text-align:center;line-height:1.2;color:#111}</style>'
        f'<div class="ion-domino" style="--ion-bg:{bg};--ion-border:{border}">'
        '<div>' + render(left_side) + '</div>'
        '<div>' + render(right_side) + '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def _nuclide_html(spec):
    """spec: A:Z:Symbole:charge"""
    mass, atomic, symbol, charge = spec.split(":")
    charge_num = int(charge)

    if charge_num == 0:
        charge_html = ""
    else:
        sign = "+" if charge_num > 0 else "−"
        n = abs(charge_num)
        charge_html = f"{'' if n == 1 else n}{sign}"

    return (
        '<div class="nuclide-wrap">'
        '<div class="nuclide-left">'
        f'<span class="nuclide-mass">{mass}</span>'
        f'<span class="nuclide-atomic">{atomic}</span>'
        '</div>'
        '<div class="nuclide-symbol-box">'
        f'<span class="nuclide-symbol">{symbol}</span>'
        f'<span class="nuclide-charge">{charge_html}</span>'
        '</div>'
        '</div>'
    )

def _composition_html(spec):
    p, n, e = spec.split(":")
    ps = "s" if p != "1" else ""
    ns = "s" if n != "1" else ""
    es = "s" if e != "1" else ""
    return (
        f'<div class="composition-wrap">'
        f'<div class="composition-title">Composé de :</div>'
        f'<ul>'
        f'<li>{p} proton{ps}</li>'
        f'<li>{n} neutron{ns}</li>'
        f'<li>{e} électron{es}</li>'
        f'</ul>'
        f'</div>'
    )

def ion_composition_domino_html(left_side, right_side, is_available=False):
    def render(side):
        if side.startswith("nuclide:"):
            return _nuclide_html(side[8:])
        if side.startswith("comp:"):
            return _composition_html(side[5:])
        return str(side)
    if is_available:
        bg = "linear-gradient(135deg,#d9ecff,#b8dcfb)"
        border = "#17476d"
    else:
        bg = "linear-gradient(135deg,#fff3b0,#ffd966)"
        border = "#8a6500"

    html = (
        '<style>.ion-comp-domino{display:grid;grid-template-columns:42% 58%;min-height:142px;background:var(--ion-bg);border:4px solid var(--ion-border);border-radius:24px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,.10)}.ion-comp-domino>div{display:flex;align-items:center;justify-content:center;padding:10px}.ion-comp-domino>div+div{border-left:3px solid var(--ion-border)}.nuclide-wrap{display:grid;grid-template-columns:34px 68px;align-items:center;width:104px;height:92px;font-family:Arial,Helvetica,sans-serif;color:#0a1620}.nuclide-left{height:72px;display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;padding-right:4px}.nuclide-mass,.nuclide-atomic{font-size:1.22rem;font-weight:800;line-height:1}.nuclide-symbol-box{position:relative;width:68px;height:72px;display:flex;align-items:center;justify-content:center}.nuclide-symbol{font-size:3.05rem;line-height:1;font-weight:900}.nuclide-charge{position:absolute;right:0px;top:-2px;font-size:1.15rem;font-weight:900;line-height:1}.composition-wrap{font-family:Arial,Helvetica,sans-serif;color:#0a1620;text-align:left;width:100%;padding-left:8px}.composition-title{font-size:1.05rem;font-weight:700;margin-bottom:4px}.composition-wrap ul{margin:0;padding-left:1.25rem;font-size:1.03rem;line-height:1.35}</style>'
        f'<div class="ion-comp-domino" style="--ion-bg:{bg};--ion-border:{border}">'
        '<div>' + render(left_side) + '</div>'
        '<div>' + render(right_side) + '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def _species_html(spec):
    """spec : symbole:charge:Z"""
    symbol, charge, atomic = spec.split(":")
    charge_num = int(charge)

    if charge_num == 0:
        charge_html = ""
    else:
        sign = "+" if charge_num > 0 else "−"
        n = abs(charge_num)
        charge_html = f"{'' if n == 1 else n}{sign}"

    symbol_html = _chem_formula_html(symbol)

    return (
        '<div class="blue-species">'
        '<span class="chem-notation">'
        f'<span class="chem-z">{atomic}</span>'
        f'<span class="chem-symbol">{symbol_html}</span>'
        f'<span class="chem-charge">{charge_html}</span>'
        '</span>'
        '</div>'
    )

def _pe_html(spec):
    p, e = spec.split(":")
    ps = "s" if p != "1" else ""
    es = "s" if e != "1" else ""
    return (
        f'<div class="blue-comp">'
        f'<div class="blue-comp-title">Composé de :</div>'
        f'<ul>'
        f'<li>{p} proton{ps}</li>'
        f'<li>{e} électron{es}</li>'
        f'</ul>'
        f'</div>'
    )

def ion_blue_domino_html(left_side, right_side, is_available=False):
    """Domino bleu avec largeur adaptée au type de contenu de chaque moitié."""
    def render(side):
        if side.startswith("species:"):
            return _species_html(side[8:])
        if side.startswith("pe:"):
            return _pe_html(side[3:])
        return str(side)

    # La composition a besoin de plus de largeur que l'écriture chimique.
    left_is_comp = left_side.startswith("pe:")
    grid_cols = "58% 42%" if left_is_comp else "42% 58%"

    # Différence visuelle entre la chaîne déjà construite et les cartes à jouer.
    if is_available:
        # Domino encore disponible : bleu clair.
        bg = "linear-gradient(135deg,#d9ecff,#b8dcfb)"
        border = "#17476d"
    else:
        # Domino déjà placé dans la chaîne : jaune clair, immédiatement identifiable.
        bg = "linear-gradient(135deg,#fff3b0,#ffd966)"
        border = "#8a6500"

    html = (
        '<style>'
        '.ion-blue-domino{display:grid;min-height:138px;border:4px solid var(--ion-border);'
        'border-radius:24px;overflow:hidden;box-shadow:0 2px 5px rgba(0,0,0,.10);'
        'background:var(--ion-bg)}'
        '.ion-blue-domino>div{display:flex;align-items:center;justify-content:center;padding:10px;min-width:0}'
        '.ion-blue-domino>div+div{border-left:3px solid var(--ion-border)}'
        '.blue-species{width:100%;height:88px;display:flex;align-items:center;justify-content:center;'
        'font-family:Arial,Helvetica,sans-serif;color:#0a1620}'
        '.chem-notation{display:inline-flex;align-items:baseline;justify-content:center;white-space:nowrap}'
        '.chem-z{font-size:1.18rem;font-weight:800;line-height:1;position:relative;top:.48em;margin-right:2px}'
        '.chem-symbol{font-size:2.75rem;line-height:1;font-weight:900;white-space:nowrap}'
        '.chem-symbol sub{font-size:.52em;vertical-align:-.22em}'
        '.chem-charge{font-size:1.05rem;font-weight:900;line-height:1;position:relative;top:-1em;margin-left:2px}'
        '.blue-comp{font-family:Arial,Helvetica,sans-serif;color:#0a1620;text-align:left;width:100%;'
        'padding-left:8px;box-sizing:border-box}'
        '.blue-comp-title{font-size:1.02rem;font-weight:700;margin-bottom:4px;white-space:nowrap}'
        '.blue-comp ul{margin:0;padding-left:1.3rem;font-size:.98rem;line-height:1.38}'
        '.blue-comp li{white-space:nowrap}'
        '</style>'
        f'<div class="ion-blue-domino" style="grid-template-columns:{grid_cols};'
        f'--ion-bg:{bg};--ion-border:{border}">'
        '<div>' + render(left_side) + '</div>'
        '<div>' + render(right_side) + '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def molecule_block(image_name):
    st.image(
        str(asset_path(image_name)),
        width=240,
    )




def glassware_block(image_name):
    """
    Affiche une illustration de verrerie sur un canevas blanc homogène.
    Les PNG sont préparés à la même taille afin d'éviter tout recadrage.
    """
    st.image(
        str(ASSETS_GLASSWARE / f"{image_name}.png"),
        use_container_width=True,
    )


def electric_domino_image(image_path, reversed_domino=False):
    """
    Charge une carte électrique complète.
    Si reversed_domino=True, coupe dans la gouttière blanche située entre
    le grand rectangle (montage) et le carré (schéma), puis échange les
    deux cadres SANS retourner leur contenu en miroir.
    """
    img = Image.open(image_path).convert("RGB")

    if not reversed_domino:
        return img

    w, h = img.size
    px = img.load()

    # On cherche la gouttière blanche verticale dans la zone centrale.
    # Une colonne de gouttière contient très peu de pixels sombres,
    # contrairement aux bordures verticales noires des deux cadres.
    x0 = int(w * 0.45)
    x1 = int(w * 0.72)

    dark_counts = []
    for x in range(x0, x1):
        dark = 0
        for y in range(2, h - 2):
            r, g, b = px[x, y]
            if r < 235 or g < 235 or b < 235:
                dark += 1
        dark_counts.append((dark, x))

    min_dark = min(v for v, _ in dark_counts)
    candidates = [x for v, x in dark_counts if v <= min_dark + max(2, int(h * 0.01))]

    # Regroupe les colonnes blanches contiguës et choisit la gouttière
    # la plus proche de la séparation attendue entre rectangle et carré.
    groups = []
    for x in candidates:
        if not groups or x > groups[-1][-1] + 1:
            groups.append([x])
        else:
            groups[-1].append(x)

    expected = int(w * 0.66)
    group = min(groups, key=lambda g: abs(((g[0] + g[-1]) / 2) - expected))
    cut = int((group[0] + group[-1]) / 2)

    # On enlève seulement la gouttière autour du point de coupe.
    # Les bordures noires des deux cadres restent dans leurs blocs.
    gap = max(2, int(w * 0.006))
    left = img.crop((0, 0, max(1, cut - gap), h))
    right = img.crop((min(w - 1, cut + gap), 0, w, h))

    # Recompose : carré/schéma à gauche, rectangle/montage à droite.
    spacer = Image.new("RGB", (gap * 2, h), "white")
    out = Image.new("RGB", (right.width + spacer.width + left.width, h), "white")
    out.paste(right, (0, 0))
    out.paste(spacer, (right.width, 0))
    out.paste(left, (right.width + spacer.width, 0))

    return out


def show_domino(level, domino_id, key=None, clickable=False, reversed_domino=False):
    level_data = LEVELS[level]

    border_state = "available" if clickable else "placed"
    safe_level = re.sub(r"[^A-Za-z0-9_-]+", "_", str(level))
    safe_domino = re.sub(r"[^A-Za-z0-9_-]+", "_", str(domino_id))
    container_key = f"domino_{border_state}_{safe_level}_{safe_domino}_{key or 'chain'}"

    # Les dominos HTML colorés gèrent eux-mêmes leur état.
    colored_variant = level_data.get("variant") in ("ions", "ion_comp", "ion_blue")

    if not colored_variant:
        border_color = "#111111" if clickable else "#d62828"
        st.markdown(
            f"<style>.st-key-{container_key}{{border:3px solid {border_color} !important;"
            f"border-radius:18px !important;padding:8px !important;}}</style>",
            unsafe_allow_html=True,
        )

    with st.container(border=not colored_variant, key=container_key):
        if level_data.get("theme") == "Électricité":
            image_file = level_data["dominos"][domino_id]
            electric_img = electric_domino_image(
                ASSETS_ELECTRICITY / image_file,
                reversed_domino=reversed_domino,
            )
            st.image(
                electric_img,
                use_container_width=True,
            )

        elif level_data.get("variant") == "ions":
            left_side, right_side = level_data["dominos"][domino_id]
            if reversed_domino:
                left_side, right_side = right_side, left_side
            ion_domino_html(left_side, right_side, is_available=clickable)

        elif level_data.get("variant") == "ion_comp":
            left_side, right_side = level_data["dominos"][domino_id]
            if reversed_domino:
                left_side, right_side = right_side, left_side
            ion_composition_domino_html(left_side, right_side, is_available=clickable)

        elif level_data.get("variant") == "ion_blue":
            left_side, right_side = level_data["dominos"][domino_id]
            if reversed_domino:
                left_side, right_side = right_side, left_side
            ion_blue_domino_html(
                left_side,
                right_side,
                is_available=clickable,
            )

        elif level_data.get("variant") in ("textes", "verrerie"):
            left_side, right_side = level_data["dominos"][domino_id]
            left, right = st.columns([1, 1], vertical_alignment="center")

            if reversed_domino:
                with left:
                    domino_side_block(right_side)
                with right:
                    domino_side_block(left_side)
            else:
                with left:
                    domino_side_block(left_side)
                with right:
                    domino_side_block(right_side)

        else:
            image_name, formula = level_data["dominos"][domino_id]
            left, right = st.columns([1, 1], vertical_alignment="center")

            if reversed_domino:
                with left:
                    formula_block(formula)
                with right:
                    molecule_block(image_name)
            else:
                with left:
                    molecule_block(image_name)
                with right:
                    formula_block(formula)

        if clickable:
            return st.button(
                "Placer",
                key=key,
                use_container_width=True,
            )

    return False


def show_turn(direction):
    align = "right" if direction == "right" else "left"

    pad = (
        "padding-right:8%;"
        if direction == "right"
        else "padding-left:8%;"
    )

    st.markdown(
        f"""
        <div style="
            text-align:{align};
            font-size:3.4rem;
            font-weight:800;
            line-height:0.8;
            {pad}
            margin-top:-0.5rem;
            margin-bottom:0.25rem;
        ">
            ↓
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_chain_snake(level, chain, per_row=4):
    for row_index, start in enumerate(range(0, len(chain), per_row)):
        row = chain[start:start + per_row]
        cols = st.columns(per_row)
        going_right = row_index % 2 == 0

        positions = (
            list(range(len(row)))
            if going_right
            else list(reversed(range(per_row - len(row), per_row)))
        )

        for domino_id, col_index in zip(row, positions):
            with cols[col_index]:
                show_domino(
                    level,
                    domino_id,
                    reversed_domino=not going_right,
                )

        if start + per_row < len(chain):
            show_turn("right" if going_right else "left")


def next_expected(level, chain):
    order = LEVELS[level]["order"]
    i = order.index(chain[-1])

    return order[(i + 1) % len(order)]


def domino_game(level, suffix="free", challenge=None, student=None):
    key = game_key(level, suffix)

    if key not in st.session_state:
        init_game(level, suffix)

    game = st.session_state[key]
    total = len(LEVELS[level]["order"])

    top1, top2, top3 = st.columns([1, 1, 2])

    with top1:
        if st.button(
            "🔄 Nouvelle partie",
            key=f"new_{suffix}_{level}",
            use_container_width=True,
        ):
            init_game(level, suffix)
            st.rerun()

    with top2:
        st.metric("Erreurs", game["errors"])

    with top3:
        st.write(f"Dominos posés : **{len(game['chain'])} / {total}**")

    if LEVELS[level].get("theme") == "Électricité":
        st.info(
            "Observe le schéma situé à l'extrémité du dernier domino posé et choisis "
            "le domino dont le montage réel correspond."
        )
    elif LEVELS[level].get("theme") == "Verrerie":
        st.info(
            "Observe le nom du matériel à l'extrémité de la chaîne puis choisis "
            "le domino qui porte son illustration."
        )
    elif LEVELS[level].get("theme") == "Ions":
        if LEVELS[level].get("variant") == "ion_comp":
            st.info(
                "Observe l'écriture de l'atome ou de l'ion et sa composition. "
                "Relie chaque écriture nucléaire au bon nombre de protons, neutrons et électrons."
            )
        elif LEVELS[level].get("variant") == "ion_blue":
            st.info(
                "Observe l'atome ou l'ion à l'extrémité de la chaîne et relie-le "
                "à la composition correcte en protons et en électrons."
            )
        else:
            st.info(
                "Observe le nom ou la formule de l'ion à l'extrémité de la chaîne, "
                "puis choisis le domino qui présente l'information correspondante."
            )
    elif LEVELS[level].get("variant") == "textes":
        st.info(
            "Observe l'extrémité libre du dernier domino puis cherche la représentation "
            "équivalente : modèle moléculaire, formule chimique ou description en mots."
        )
    else:
        st.info(
            "Observe l'extrémité libre du dernier domino posé et choisis, "
            "parmi tes cartes, celle dont le modèle correspond."
        )

    st.markdown("### Chaîne construite")
    show_chain_snake(level, game["chain"], per_row=4)

    if game["remaining"]:
        st.markdown("### Dominos disponibles")

        expected = next_expected(level, game["chain"])
        clicked = None

        for row_start in range(0, len(game["remaining"]), 3):
            row = game["remaining"][row_start:row_start + 3]
            cols = st.columns(3)

            for i, did in enumerate(row):
                with cols[i]:
                    if show_domino(
                        level,
                        did,
                        key=f"pick_{suffix}_{level}_{did}",
                        clickable=True,
                        reversed_domino=False,
                    ):
                        clicked = did

        if clicked:
            if clicked == expected:
                game["chain"].append(clicked)
                game["remaining"].remove(clicked)
                st.rerun()
            else:
                game["errors"] += 1
                st.error(
                    "Ce domino ne correspond pas. "
                    "Observe à nouveau l'extrémité de la chaîne."
                )

    else:
        elapsed = int(time.time() - game["started"])

        st.markdown("---")
        st.markdown("## 🎉 Niveau terminé !")

        r1, r2, r3 = st.columns(3)

        with r1:
            st.metric("Erreurs", game["errors"])

        with r2:
            st.metric(
                "Temps",
                f"{elapsed // 60} min {elapsed % 60:02d} s",
            )

        with r3:
            st.metric("Dominos", f"{total}/{total}")

        if game["errors"] == 0:
            st.success("🎯 Badge obtenu : Sans faute")

        if challenge and student and not game["saved"]:
            ok, result = save_result(
                student,
                challenge,
                game["errors"],
                elapsed,
            )

            game["saved"] = True

            if ok:
                st.success(
                    f"✅ Résultat enregistré — tentative "
                    f"{result['attempt']} / {challenge['max_attempts']}."
                )
            else:
                st.warning(result)

        if challenge and student:
            used = attempts_used(student, challenge)
            remaining_attempts = max(
                0,
                int(challenge["max_attempts"]) - used,
            )

            if remaining_attempts > 0:
                if st.button(
                    f"🔄 Rejouer le défi "
                    f"({remaining_attempts} tentative(s) restante(s))",
                    key=f"retry_challenge_{challenge['code']}",
                    use_container_width=True,
                ):
                    init_game(level, suffix)
                    st.rerun()
            else:
                st.info(
                    "🏁 Toutes les tentatives autorisées "
                    "pour ce défi ont été utilisées."
                )

            if st.button(
                "🚪 Quitter le défi",
                key=f"leave_{challenge['code']}",
                use_container_width=True,
            ):
                st.session_state.pop("challenge_student", None)
                st.session_state.pop("active_challenge", None)
                st.query_params.clear()
                go("home")

        else:
            theme = LEVELS[level].get("theme", "Molécules")
            theme_levels = levels_for_theme(theme)
            current_index = theme_levels.index(level)

            st.markdown("### Que veux-tu faire maintenant ?")

            left, right = st.columns(2)

            with left:
                if st.button(
                    "🔄 Rejouer le même niveau",
                    key=f"replay_{theme}_{level}",
                    use_container_width=True,
                ):
                    init_game(level, suffix)
                    st.rerun()

            with right:
                if current_index < len(theme_levels) - 1:
                    next_level = theme_levels[current_index + 1]

                    if st.button(
                        f"➡️ Passer au niveau suivant : "
                        f"{LEVELS[next_level]['emoji']} {next_level}",
                        key=f"next_{theme}_{level}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.selected_level = next_level
                        init_game(next_level, suffix)
                        st.rerun()
                else:
                    first = theme_levels[0]
                    if st.button(
                        f"🏆 Recommencer depuis le niveau "
                        f"{LEVELS[first]['emoji']} {first}",
                        key=f"restart_all_{theme}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.selected_level = first
                        init_game(first, suffix)
                        st.rerun()



# ============================================================
# DOMINOS — MODE COLLABORATIF
# ============================================================

def collab_set_proposal(team, domino_id, student_id):
    team["game"]["proposal"] = {
        "domino_id": domino_id,
        "student_id": student_id,
        "proposed_at": time.time(),
    }
    save_collab_team(team)


def collab_cancel_proposal(team):
    team["game"]["proposal"] = None
    save_collab_team(team)


def collab_validate_proposal(team, challenge):
    game = team["game"]
    proposal = game.get("proposal")
    if not proposal:
        return None

    domino_id = proposal["domino_id"]
    expected = next_expected(challenge["level"], game["chain"])
    active_index = int(game["turn_index"]) % len(team["members"])
    active = team["members"][active_index]

    team["members"][active_index]["turns"] = (
        int(team["members"][active_index].get("turns", 0)) + 1
    )

    correct = domino_id == expected

    if correct:
        game["chain"].append(domino_id)
        if domino_id in game["remaining"]:
            game["remaining"].remove(domino_id)
    else:
        game["errors"] += 1
        # L'erreur reste collective pour le score de l'équipe, mais on conserve
        # l'élève dont c'était le tour au moment de la validation afin de fournir
        # au professeur un détail factuel sans transformer le score en évaluation individuelle.
        game.setdefault("error_details", []).append(
            {
                "student_id": active["id"],
                "first_name": active["first_name"],
                "last_initial": active["last_initial"],
                "domino_id": domino_id,
                "validated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    game["proposal"] = None
    game["turn_index"] = (active_index + 1) % len(team["members"])

    if not game["remaining"]:
        game["finished_at"] = time.time()
        team["status"] = "finished"

    save_collab_team(team)

    if team["status"] == "finished":
        save_collab_result(team, challenge)

    return correct


@st.fragment(run_every=2)
def collaborative_domino_fragment(student, challenge, team_code):
    team = get_collab_team(
        challenge["_teacher_id"],
        challenge["code"],
        team_code,
    )

    if not team:
        st.error("Cette équipe n'existe plus.")
        return

    members = team.get("members", [])
    target = int(team.get("target_size", challenge.get("team_size", 4)))

    st.markdown(f"### 👥 Équipe {team_code} — {len(members)}/{target}")
    st.write(
        " • ".join(
            f"**{m['first_name']} {m['last_initial']}.**"
            for m in members
        )
    )

    departures = team.get("departures", [])
    if departures:
        latest_departure = departures[-1]
        st.warning(
            f"⚠️ {latest_departure['first_name']} "
            f"{latest_departure['last_initial']}. a quitté l'équipe. "
            "La partie continue avec les élèves restants."
        )

    if team.get("status") == "lobby":
        st.info(
            "En attente des autres membres. "
            "Communiquez le code d'équipe à vos camarades."
        )
        st.markdown(
            f"<div style='text-align:center;font-size:3rem;font-weight:800;"
            f"letter-spacing:.35rem;padding:.6rem'>{team_code}</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "La partie démarre automatiquement quand l'équipe est complète."
        )
        return

    game = team.get("game")
    if not game:
        st.warning("La partie n'est pas encore initialisée.")
        return

    if team.get("status") == "finished":
        elapsed = int((game.get("finished_at") or time.time()) - game["started"])
        st.success("🎉 Partie collaborative terminée !")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Erreurs", game["errors"])
        with c2:
            st.metric("Temps", f"{elapsed // 60} min {elapsed % 60:02d} s")
        with c3:
            st.metric(
                "Dominos",
                f"{len(game['chain'])}/{len(LEVELS[challenge['level']]['order'])}",
            )

        st.markdown("### Participation")
        for m in members:
            st.write(
                f"• {m['first_name']} {m['last_initial']}. "
                f"— {m.get('turns', 0)} tour(s)"
            )

        departures = team.get("departures", [])
        if departures:
            st.markdown("### Élèves ayant quitté la partie")
            for departure in departures:
                st.write(
                    f"• {departure['first_name']} "
                    f"{departure['last_initial']}."
                )

        st.info("Le résultat de l'équipe a été envoyé à l'espace professeur.")
        return

    active_index = int(game["turn_index"]) % len(members)
    active = members[active_index]
    is_active = active["id"] == student["id"]

    if is_active:
        st.success(
            f"🎯 **À toi de jouer, {student['first_name']} !** "
            "Discute avec ton équipe avant de proposer."
        )
    else:
        st.info(
            f"👀 **C'est à {active['first_name']} {active['last_initial']}. de jouer.** "
            "Aidez-vous oralement."
        )

    st.markdown("### Chaîne construite")
    show_chain_snake(challenge["level"], game["chain"], per_row=4)

    proposal = game.get("proposal")

    if proposal:
        proposed_id = proposal["domino_id"]
        proposer = next(
            (m for m in members if m["id"] == proposal["student_id"]),
            active,
        )

        st.markdown(
            f"### 🤔 Proposition de {proposer['first_name']} "
            f"{proposer['last_initial']}."
        )

        proposal_left, proposal_center, proposal_right = st.columns(3)

        with proposal_center:
            show_domino(
                challenge["level"],
                proposed_id,
                clickable=False,
            )

        st.warning(
            "Discutez ensemble avant de valider. "
            "La réponse n'a pas encore été vérifiée."
        )

        if is_active:
            a, b = st.columns(2)
            with a:
                if st.button(
                    "✅ Valider notre choix",
                    key=f"collab_validate_{team_code}_{proposed_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    correct = collab_validate_proposal(team, challenge)
                    st.toast("✅ Bonne association !" if correct else "❌ Mauvais domino.")
                    st.rerun(scope="fragment")
            with b:
                if st.button(
                    "🔄 Changer de domino",
                    key=f"collab_cancel_{team_code}_{proposed_id}",
                    use_container_width=True,
                ):
                    collab_cancel_proposal(team)
                    st.rerun(scope="fragment")
        else:
            st.caption(
                "Seul l'élève dont c'est le tour peut valider ou changer la proposition."
            )
        return

    st.markdown("### Dominos disponibles")
    clicked = None
    remaining = game.get("remaining", [])

    for row_start in range(0, len(remaining), 3):
        row = remaining[row_start:row_start + 3]
        cols = st.columns(3)
        for i, did in enumerate(row):
            with cols[i]:
                if is_active:
                    if show_domino(
                        challenge["level"],
                        did,
                        key=f"collab_pick_{team_code}_{did}",
                        clickable=True,
                        reversed_domino=False,
                    ):
                        clicked = did
                else:
                    show_domino(
                        challenge["level"],
                        did,
                        clickable=False,
                        reversed_domino=False,
                    )

    if clicked and is_active:
        collab_set_proposal(team, clicked, student["id"])
        st.rerun(scope="fragment")


def collaborative_challenge_page(student, challenge):
    team_code = st.session_state.get("collab_team_code")

    if not team_code:
        st.markdown("## 👥 Mode collaboratif")
        st.write(
            f"Équipes de **{challenge.get('team_size', 4)} élèves**. "
            "Chaque élève utilise son propre Chromebook."
        )
        st.info(
            "Pour cette partie, créez une nouvelle équipe ou saisissez le code "
            "de l'équipe que vous souhaitez rejoindre. Si une équipe a déjà commencé "
            "mais qu'une place s'est libérée, un élève peut la rejoindre sans "
            "réinitialiser la partie."
        )

        left, right = st.columns(2)

        with left:
            st.markdown("### Créer une équipe")
            st.write(
                "Le premier élève de la table crée l'équipe "
                "et communique le code à ses camarades."
            )
            if st.button(
                "➕ Créer mon équipe",
                type="primary",
                use_container_width=True,
                key="create_collab_team_button",
            ):
                code, team, error = create_collab_team(student, challenge)
                if error:
                    st.error(error)
                else:
                    st.session_state.collab_team_code = code
                    st.rerun()

        with right:
            st.markdown("### Rejoindre une équipe")
            join_code = st.text_input(
                "Code équipe",
                max_chars=3,
                placeholder="Ex. 427",
                key="join_team_code",
            )
            if st.button(
                "👥 Rejoindre l'équipe",
                use_container_width=True,
                key="join_collab_team_button",
            ):
                code, team, error = join_collab_team(
                    student,
                    challenge,
                    join_code,
                )
                if error:
                    st.error(error)
                else:
                    st.session_state.collab_team_code = code
                    st.rerun()
        return

    collaborative_domino_fragment(student, challenge, team_code)

    st.markdown("---")
    if st.button(
        "🚪 Quitter le défi collaboratif",
        use_container_width=True,
        key="leave_collab_challenge",
    ):
        leave_collab_team(
            student,
            challenge,
            team_code,
        )

        for key in ["collab_team_code", "active_challenge", "challenge_student"]:
            st.session_state.pop(key, None)

        st.query_params.clear()
        go("home")


def levels_for_theme(theme):
    if theme == "Électricité":
        return ELECTRICITY_LEVEL_NAMES
    if theme == "Verrerie":
        return GLASSWARE_LEVEL_NAMES
    if theme == "Ions":
        return ION_LEVEL_NAMES
    return MOLECULE_LEVEL_NAMES


def game_credit(theme):
    if theme == "Électricité":
        st.caption(
            "Adaptation numérique du jeu « Schématisation et circuits électriques — "
            "Jeu de Dominos » de Stéphane Bois et Raphaëlle Darne — licence CC BY-NC-SA."
        )
    elif theme == "Molécules":
        st.caption(
            "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes — licence CC BY-NC-SA."
        )
    elif theme == "Verrerie":
        st.caption(
            "Illustrations de matériel de laboratoire créées pour la Ludothèque Physique-Chimie."
        )
    elif theme == "Ions":
        st.caption(
            "Dominos construits à partir de la liste d'ions utilisée en cours."
        )


# ============================================================
# NAVIGATION ÉLÈVE
# ============================================================

def page_home():
    """Accueil modernisé avec fond commun — navigation inchangée."""

    bg_path = Path("assets/background_ludotheque.png")
    if not bg_path.exists():
        st.error("Le fond assets/background_ludotheque.png est introuvable.")
        return

    bg_b64 = base64.b64encode(bg_path.read_bytes()).decode("utf-8")

    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/png;base64,{bg_b64}") !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            background-size: 100% 100% !important;
            background-attachment: fixed !important;
            background-color: #061a42 !important;
            overflow-x: hidden !important;
        }}

        .stApp {{
            background: transparent !important;
        }}

        .block-container {{
            max-width: 1180px !important;
            padding-top: 0.25rem !important;
            padding-bottom: 0.45rem !important;
        }}

        .home-modern-head {{
            text-align: center;
            color: white;
            padding: 0 0 .5rem 0;
        }}

        .home-modern-icon {{
            font-size: 2.2rem;
            line-height: 1;
            margin-bottom: .05rem;
            filter: drop-shadow(0 6px 14px rgba(0,215,255,.28));
        }}

        .home-modern-title {{
            font-size: clamp(2rem, 3vw, 2.85rem);
            line-height: 1.02;
            font-weight: 900;
            letter-spacing: -0.04em;
            margin: 0;
            text-shadow: 0 6px 20px rgba(0,0,0,.30);
        }}

        .home-modern-subtitle {{
            font-size: clamp(.92rem, 1.2vw, 1.12rem);
            margin-top: .25rem;
            color: rgba(255,255,255,.96);
        }}

        .home-modern-line {{
            width: 115px;
            height: 3px;
            margin: .45rem auto 0 auto;
            border-radius: 999px;
            background: linear-gradient(90deg,#00d9ff,#36e4d2);
            box-shadow: 0 0 15px rgba(0,217,255,.35);
        }}

        .st-key-home_card_free,
        .st-key-home_card_challenge,
        .st-key-home_card_teacher {{
            border-radius: 20px !important;
            padding: 0 !important;
            overflow: hidden !important;
            background: rgba(255,255,255,.985) !important;
            box-shadow: 0 18px 40px rgba(0,0,0,.24) !important;
            border: 1px solid rgba(255,255,255,.80) !important;
        }}

        .st-key-home_card_free {{ border-top: 6px solid #1f91ff !important; }}
        .st-key-home_card_challenge {{ border-top: 6px solid #21c65b !important; }}
        .st-key-home_card_teacher {{ border-top: 6px solid #8b5cf6 !important; }}

        .modern-home-card {{
            min-height: 310px;
            padding: .65rem 1rem .35rem 1rem;
            text-align: center;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        .modern-card-visual {{
            width: 145px;
            height: 118px;
            border-radius: 44% 56% 50% 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto .35rem auto;
            font-size: 4.2rem;
            line-height: 1;
            position: relative;
            overflow: visible;
        }}

        .visual-free {{
            background:
                radial-gradient(circle at 50% 50%, rgba(205,233,255,.96), rgba(232,246,255,.74) 55%, rgba(255,255,255,0) 72%);
            filter: drop-shadow(0 7px 14px rgba(25,110,225,.13));
        }}

        .visual-challenge {{
            background:
                radial-gradient(circle at 50% 50%, rgba(217,249,226,.98), rgba(235,255,240,.76) 55%, rgba(255,255,255,0) 72%);
            filter: drop-shadow(0 7px 14px rgba(22,163,74,.13));
        }}

        .visual-teacher {{
            background:
                radial-gradient(circle at 50% 50%, rgba(234,225,255,.98), rgba(246,241,255,.78) 55%, rgba(255,255,255,0) 72%);
            filter: drop-shadow(0 7px 14px rgba(109,40,217,.13));
        }}

        .visual-free .v-main,
        .visual-challenge .v-main,
        .visual-teacher .v-main {{
            position: relative;
            z-index:2;
            transform: translateY(2px);
        }}

        .visual-free .v-mini,
        .visual-challenge .v-mini,
        .visual-teacher .v-mini {{
            position:absolute;
            font-size:1.25rem;
            opacity:.82;
            filter:none;
        }}

        .visual-free .m1 {{ left:14px; top:54px; }}
        .visual-free .m2 {{ right:8px; bottom:35px; }}
        .visual-free .m3 {{ right:32px; top:18px; }}

        .visual-challenge .m1 {{ left:14px; top:62px; }}
        .visual-challenge .m2 {{ right:12px; top:42px; }}
        .visual-challenge .m3 {{ right:24px; bottom:28px; }}

        .visual-teacher .m1 {{ left:10px; bottom:30px; }}
        .visual-teacher .m2 {{ right:12px; top:42px; }}
        .visual-teacher .m3 {{ right:28px; bottom:24px; }}

        .modern-card-title {{
            color: #0b2b63;
            font-size: 1.35rem;
            font-weight: 900;
            line-height: 1.08;
            margin: .02rem 0 .32rem 0;
            letter-spacing: -0.03em;
        }}

        .modern-card-text {{
            color: #334b70;
            font-size: .88rem;
            line-height: 1.30;
            max-width: 300px;
            min-height: 48px;
            margin: 0 auto .32rem auto;
        }}

        .modern-card-mini-line {{
            width: 34px;
            height: 3px;
            border-radius: 999px;
            margin: .12rem auto 0 auto;
        }}

        .mini-blue {{ background:#1f91ff; }}
        .mini-green {{ background:#21c65b; }}
        .mini-purple {{ background:#8b5cf6; }}

        .st-key-home_card_free div[data-testid="stButton"] > button,
        .st-key-home_card_challenge div[data-testid="stButton"] > button,
        .st-key-home_card_teacher div[data-testid="stButton"] > button {{
            width: calc(100% - 1.6rem) !important;
            margin: .05rem .8rem .7rem .8rem !important;
            min-height: 2.75rem !important;
            border-radius: 17px !important;
            font-size: .95rem !important;
            font-weight: 850 !important;
            box-shadow: none !important;
        }}

        .st-key-home_card_free div[data-testid="stButton"] > button {{
            background: linear-gradient(90deg,#e2f1ff,#cfe8ff) !important;
            color: #0876ea !important;
            border: 1px solid #c6e1ff !important;
        }}

        .st-key-home_card_challenge div[data-testid="stButton"] > button {{
            background: linear-gradient(90deg,#e1f9e8,#ccf1d8) !important;
            color: #10a044 !important;
            border: 1px solid #c5ebd0 !important;
        }}

        .st-key-home_card_teacher div[data-testid="stButton"] > button {{
            background: linear-gradient(90deg,#f0eaff,#e1d5ff) !important;
            color: #6d28d9 !important;
            border: 1px solid #dacdff !important;
        }}

        .st-key-home_card_free div[data-testid="stButton"] > button:hover,
        .st-key-home_card_challenge div[data-testid="stButton"] > button:hover,
        .st-key-home_card_teacher div[data-testid="stButton"] > button:hover {{
            transform: translateY(-1px);
            filter: brightness(.98);
        }}

        .home-modern-bottom {{
            text-align:center;
            color:#0ed7ed;
            margin-top:.18rem;
        }}

        .home-modern-icons {{
            font-size:2.35rem;
            letter-spacing:.65rem;
            margin-left:.65rem;
            opacity:.95;
            text-shadow:0 0 18px rgba(0,210,255,.25);
        }}

        .home-modern-brand {{
            margin-top:.45rem;
            font-size:.82rem;
            color:rgba(255,255,255,.92);
        }}

        .home-modern-brand b {{
            color:#13d8e8;
        }}

        .footer-note {{
            display:none !important;
        }}

        @media (max-width: 1000px) {{
            .modern-home-card {{ min-height: 385px; }}
            .modern-card-visual {{
                width: 165px;
                height: 150px;
                font-size: 5rem;
            }}
            .home-modern-icons {{ letter-spacing:.7rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="home-modern-head">
            <div class="home-modern-icon">⚗️</div>
            <div class="home-modern-title">Que veux-tu faire aujourd’hui ?</div>
            <div class="home-modern-subtitle">Choisis ton espace pour commencer.</div>
            <div class="home-modern-line"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    identity_label = current_app_user_label()
    info_col, logout_col = st.columns([5, 1])
    with info_col:
        st.markdown(
            f'<div style="color:white;font-weight:800;padding:.35rem 0 .45rem 0;">'
            f'👤 Connecté : {identity_label}</div>',
            unsafe_allow_html=True,
        )
    with logout_col:
        if st.button("Déconnexion", key="home_logout", use_container_width=True):
            clear_app_session()
            st.rerun()

    is_teacher = st.session_state.get("app_user_type") == "teacher"
    home_cols = st.columns(3 if is_teacher else 2, gap="large")
    c1, c2 = home_cols[0], home_cols[1]
    c3 = home_cols[2] if is_teacher else None

    with c1:
        with st.container(key="home_card_free"):
            st.markdown(
                """
                <div class="modern-home-card">
                    <div class="modern-card-visual visual-free">
                        <span class="v-mini m1">⚛️</span>
                        <span class="v-mini m2">🧬</span>
                        <span class="v-mini m3">✦</span>
                        <span class="v-main">🎮</span>
                    </div>
                    <div class="modern-card-title">Mon espace d’entraînement</div>
                    <div class="modern-card-text">
                        Révise, entraîne-toi et<br>joue à ton rythme.
                    </div>
                    <div class="modern-card-mini-line mini-blue"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button(
                "Jouer   →",
                key="home_free",
                use_container_width=True,
                on_click=set_page,
                args=("free_activity",),
            )

    with c2:
        with st.container(key="home_card_challenge"):
            st.markdown(
                """
                <div class="modern-home-card">
                    <div class="modern-card-visual visual-challenge">
                        <span class="v-mini m1">⚛️</span>
                        <span class="v-mini m2">⚡</span>
                        <span class="v-mini m3">🧬</span>
                        <span class="v-main">🏆</span>
                    </div>
                    <div class="modern-card-title">Participer à un défi</div>
                    <div class="modern-card-text">
                        Rejoins le défi lancé par<br>ton professeur.
                    </div>
                    <div class="modern-card-mini-line mini-green"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button(
                "Rejoindre   →",
                key="home_challenge",
                type="primary",
                use_container_width=True,
                on_click=set_page,
                args=("challenge",),
            )

    if is_teacher and c3 is not None:
        with c3:
            with st.container(key="home_card_teacher"):
                st.markdown(
                    """
                    <div class="modern-home-card">
                        <div class="modern-card-visual visual-teacher">
                            <span class="v-mini m1">📊</span>
                            <span class="v-mini m2">🧪</span>
                            <span class="v-mini m3">🧬</span>
                            <span class="v-main">🔐</span>
                        </div>
                        <div class="modern-card-title">Espace professeur</div>
                        <div class="modern-card-text">
                            Gère tes classes, tes élèves,<br>tes défis et consulte les résultats.
                        </div>
                        <div class="modern-card-mini-line mini-purple"></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.button(
                    "Accéder   →",
                    key="home_teacher",
                    use_container_width=True,
                    on_click=set_page,
                    args=("teacher",),
                )

    st.markdown(
        """
        <div class="home-modern-bottom">
            <div class="home-modern-icons">🧲  🌡️  💡  ⚗️</div>
            <div class="home-modern-brand">Ludothèque <b>Physique-Chimie</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def states_matter_available_for_current_user():
    """Le professeur voit tout ; l'élève pilote voit la notion seulement si sa classe l'a ouverte."""
    if st.session_state.get("app_user_type") == "teacher":
        return True

    if st.session_state.get("app_user_type") != "student":
        return False

    student = st.session_state.get("app_student") or {}
    teacher_id = student.get("_teacher_id")

    # Pour les autres professeurs, on ne change pas encore le fonctionnement général.
    if not content_pilot_enabled_for_teacher(teacher_id, ""):
        return False

    return content_is_open_for_class(
        "exercise_states_matter",
        student.get("class_name", ""),
        teacher_id,
    )


def page_free_activity():
    hero()
    back_button("home")

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Choix de l’activité</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Choisissez votre activité</div>',
        unsafe_allow_html=True,
    )

    states_ready = states_matter_available_for_current_user()

    cols = st.columns(5)

    activities = [
        ("🁢", "Dominos", "Associez les dominos et construisez le bon chemin.", "card-blue", False),
        ("🧠", "Memory", "Retrouvez les paires correspondantes.", "card-pink", True),
        ("🔗", "Associations", "Associez les bonnes réponses.", "card-cyan", True),
        ("📝", "Exercices", "Entraînez-vous avec des questions autocorrigées et des explications.", "card-purple", not states_ready),
        ("⚡", "Défis rapides", "De courts défis pour tester vos connaissances.", "card-orange", True),
    ]

    for i, (icon, title, card_text, color, soon) in enumerate(activities):
        with cols[i]:
            nav_card(icon, title, card_text, color, coming_soon=soon)

            if title == "Dominos":
                st.button(
                    "Choisir",
                    key="choose_dominos",
                    use_container_width=True,
                    on_click=set_page,
                    args=("free_theme",),
                )
            elif title == "Exercices" and states_ready:
                st.button(
                    "Choisir",
                    key="choose_exercises",
                    use_container_width=True,
                    on_click=set_page,
                    args=("exercise_topics",),
                )
            else:
                st.button(
                    "Bientôt disponible",
                    key=f"soon_{title}",
                    use_container_width=True,
                    disabled=True,
                )


STATES_MATTER_QUESTIONS = [
    {
        "question": "À température ambiante, dans quel état se trouve un glaçon ?",
        "choices": ["Solide", "Liquide", "Gaz"],
        "answer": "Solide",
        "hint": "Un glaçon garde sa forme propre lorsqu'on le pose sur une surface.",
        "explanation": "Un solide possède une forme propre : le glaçon conserve sa forme tant qu'il ne fond pas.",
    },
    {
        "question": "On verse de l'eau d'une bouteille dans un bécher. Que fait l'eau ?",
        "choices": [
            "Elle conserve exactement la forme de la bouteille",
            "Elle prend la forme du récipient qui la contient",
            "Elle occupe obligatoirement tout le volume du bécher",
        ],
        "answer": "Elle prend la forme du récipient qui la contient",
        "hint": "Demande-toi si un liquide possède une forme propre.",
        "explanation": "Un liquide n'a pas de forme propre : il prend la forme du récipient qui le contient.",
    },
    {
        "question": "Quelle propriété caractérise un gaz placé dans un récipient fermé ?",
        "choices": [
            "Il reste uniquement au fond",
            "Il conserve toujours le même petit volume",
            "Il occupe tout l'espace disponible",
        ],
        "answer": "Il occupe tout l'espace disponible",
        "hint": "Pense à l'air dans une bouteille fermée, même lorsque la bouteille semble vide.",
        "explanation": "Un gaz se répartit dans tout le volume disponible du récipient.",
    },
    {
        "question": "Dans quel état les particules sont-elles très proches les unes des autres et ordonnées ?",
        "choices": ["Solide", "Liquide", "Gaz"],
        "answer": "Solide",
        "hint": "Dans cet état, la matière garde une forme propre.",
        "explanation": "Dans le modèle particulaire d'un solide, les particules sont très proches et organisées de manière ordonnée.",
    },
    {
        "question": "Dans quel état les particules sont-elles proches mais désordonnées et peuvent se déplacer les unes par rapport aux autres ?",
        "choices": ["Solide", "Liquide", "Gaz"],
        "answer": "Liquide",
        "hint": "Cet arrangement permet à la matière de s'écouler et de changer de forme.",
        "explanation": "Dans un liquide, les particules restent proches mais sont désordonnées et mobiles les unes par rapport aux autres.",
    },
    {
        "question": "Dans quel état les particules sont-elles très espacées ?",
        "choices": ["Solide", "Liquide", "Gaz"],
        "answer": "Gaz",
        "hint": "C'est l'état qui peut occuper tout l'espace disponible.",
        "explanation": "Dans un gaz, les particules sont très espacées et se déplacent dans tout le volume disponible.",
    },
    {
        "question": "On incline doucement un récipient contenant de l'eau au repos. Comment se comporte la surface libre de l'eau ?",
        "choices": [
            "Elle reste horizontale",
            "Elle devient verticale",
            "Elle garde exactement l'orientation du fond du récipient",
        ],
        "answer": "Elle reste horizontale",
        "hint": "Observe la surface de l'eau dans un verre que l'on incline légèrement.",
        "explanation": "Au repos, la surface libre d'un liquide reste horizontale, quelle que soit la forme du récipient.",
    },
    {
        "question": "Parmi ces propositions, laquelle décrit correctement l'air ?",
        "choices": [
            "L'air est un mélange de gaz",
            "L'air est un liquide invisible",
            "L'air n'est pas de la matière",
        ],
        "answer": "L'air est un mélange de gaz",
        "hint": "L'air contient notamment du diazote et du dioxygène.",
        "explanation": "L'air est un mélange de plusieurs gaz, principalement du diazote et du dioxygène. C'est bien de la matière et il occupe un volume.",
    },
]


def page_exercise_topics():
    hero()
    back_button("free_activity")

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">📝 Exercices d’entraînement</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Seuls les exercices ouverts par ton professeur apparaissent ici."
    )

    exercises = []

    session1 = "Séance 1 — États de la matière et mélanges"
    session2 = "Séance 2 — Atomes, molécules et éléments chimiques"

    if resource_is_available_for_current_user("exercise1_states_water"):
        exercises.append({
            "session": session1,
            "icon": "💧",
            "title": "Exercice 1 — Identifier les états de l’eau",
            "description": "Associe chaque situation au bon état physique : solide, liquide ou gazeux.",
            "color": "card-cyan",
            "page": "exercise1_states_water",
            "key": "start_ex14_states_water",
        })

    if resource_is_available_for_current_user("exercise2_water_properties"):
        exercises.append({
            "session": session1,
            "icon": "🧊",
            "title": "Exercice 2 — Les particularités des états de l’eau",
            "description": "Observe les trois images A, B et C puis attribue la bonne lettre à chaque étiquette.",
            "color": "card-blue",
            "page": "exercise2_water_properties",
            "key": "start_ex2_water_properties",
        })

    if resource_is_available_for_current_user("exercise3_particle_models"):
        exercises.append({
            "session": session1,
            "icon": "🔬",
            "title": "Exercice 3 — Comprendre la modélisation",
            "description": "Observe la disposition des molécules et écris l’état de la matière représenté.",
            "color": "card-purple",
            "page": "exercise3_particle_models",
            "key": "start_ex3_particle_models",
        })

    if resource_is_available_for_current_user("exercise4_oxygen_bottle"):
        exercises.append({
            "session": session1,
            "icon": "🫧",
            "title": "Exercice 4 — Propriétés et bouteille de dioxygène",
            "description": "Relie propriétés moléculaires, zones de la bouteille et construction d’un modèle.",
            "color": "card-green",
            "page": "exercise4_oxygen_bottle",
            "key": "start_ex4_oxygen_bottle",
        })

    if resource_is_available_for_current_user("exercise5_seawater_mixture"):
        exercises.append({
            "session": session1,
            "icon": "🌊",
            "title": "Exercice 5 — Modéliser un mélange : l’eau de mer",
            "description": "Observe deux modèles microscopiques et distingue corps pur et mélange.",
            "color": "card-cyan",
            "page": "exercise5_seawater_mixture",
            "key": "start_ex5_seawater_mixture",
        })

    if resource_is_available_for_current_user("exercise6_water_alcohol_volume"):
        exercises.append({
            "session": session1,
            "icon": "🧪",
            "title": "Exercice 6 — Le mystère du volume perdu : eau + alcool",
            "description": "Explique un volume final inférieur à la somme des volumes initiaux et modélise le mélange à l’échelle microscopique.",
            "color": "card-purple",
            "page": "exercise6_water_alcohol_volume",
            "key": "start_ex6_water_alcohol_volume",
        })

    if resource_is_available_for_current_user("exercise7_solid_mixtures_alloys"):
        exercises.append({
            "session": session1,
            "icon": "🔑",
            "title": "Exercice 7 — Les mélanges solides : les alliages",
            "description": "Découvre le laiton et l’acier puis distingue alliage d’insertion et alliage de substitution.",
            "color": "card-green",
            "page": "exercise7_solid_mixtures_alloys",
            "key": "start_ex7_solid_mixtures_alloys",
        })

    if resource_is_available_for_current_user("exercise8_element_symbols"):
        exercises.append({
            "session": session2,
            "icon": "🧩",
            "title": "Exercice 8 — Symboles des éléments",
            "description": "Utilise le tableau périodique pour associer noms et symboles, puis enquête sur le symbole W du tungstène.",
            "color": "card-blue",
            "page": "exercise8_element_symbols",
            "key": "start_ex8_element_symbols",
        })

    if resource_is_available_for_current_user("exercise9_atom_or_molecule"):
        exercises.append({
            "session": session2,
            "icon": "⚛️",
            "title": "Exercice 9 — Atome ou molécule ?",
            "description": "Classe différentes écritures chimiques et fais attention au piège CO / Co.",
            "color": "card-cyan",
            "page": "exercise9_atom_or_molecule",
            "key": "start_ex9_atom_or_molecule",
        })

    if resource_is_available_for_current_user("exercise10_ethanol"):
        exercises.append({
            "session": session2,
            "icon": "🧪",
            "title": "Exercice 10 — Éthanol",
            "description": "Observe le modèle moléculaire de l’éthanol, compte les atomes puis écris sa formule.",
            "color": "card-purple",
            "page": "exercise10_ethanol",
            "key": "start_ex10_ethanol",
        })

    if resource_is_available_for_current_user("exercise11_nitrous_oxide"):
        exercises.append({
            "session": session2,
            "icon": "💨",
            "title": "Exercice 11 — Protoxyde d’azote",
            "description": "Travaille sur l’azote, le diazote, le dioxyde d’azote et le protoxyde d’azote.",
            "color": "card-green",
            "page": "exercise11_nitrous_oxide",
            "key": "start_ex11_nitrous_oxide",
        })

    if resource_is_available_for_current_user("exercise12_caffeine"):
        exercises.append({
            "session": session2,
            "icon": "☕",
            "title": "Exercice 12 — Caféine",
            "description": "Lis la formule de la caféine, détaille sa composition et compte tous ses atomes.",
            "color": "card-orange",
            "page": "exercise12_caffeine",
            "key": "start_ex12_caffeine",
        })

    if resource_is_available_for_current_user("exercise13_names_formulas"):
        exercises.append({
            "session": session2,
            "icon": "🧬",
            "title": "Exercice 13 — Noms et formules",
            "description": "Observe quatre modèles moléculaires et retrouve leur nom ainsi que leur formule.",
            "color": "card-blue",
            "page": "exercise13_names_formulas",
            "key": "start_ex13_names_formulas",
        })

    if resource_is_available_for_current_user("exercise14_molecule_formulas"):
        exercises.append({
            "session": session2,
            "icon": "🔎",
            "title": "Exercice 14 — Formules de molécules",
            "description": "Observe deux nouveaux modèles moléculaires et retrouve leur formule.",
            "color": "card-cyan",
            "page": "exercise14_molecule_formulas",
            "key": "start_ex14_molecule_formulas",
        })

    if states_matter_available_for_current_user():
        exercises.append({
            "session": session1,
            "icon": "🧊",
            "title": "Entraînement — États de la matière",
            "description": "8 questions autocorrigées sur les solides, liquides, gaz et le modèle particulaire.",
            "color": "card-purple",
            "page": "exercise_states_matter",
            "key": "start_states_matter",
        })

    if not exercises:
        st.info("Aucun exercice n'est encore ouvert pour ta classe.")
        return

    grouped = {}
    for exercise in exercises:
        grouped.setdefault(exercise["session"], []).append(exercise)

    session_order = [session1, session2]

    for session_name in session_order:
        session_exercises = grouped.get(session_name, [])
        if not session_exercises:
            continue

        # Séance 1 fermée par défaut ; séance 2 ouverte par défaut.
        default_open = session_name == session2

        with st.expander(
            f"{session_name}  ·  {len(session_exercises)} exercice(s)",
            expanded=default_open,
        ):
            for exercise in session_exercises:
                c1, c_mid, c2 = st.columns([4.5, .35, 1.5])

                with c1:
                    nav_card(
                        exercise["icon"],
                        exercise["title"],
                        exercise["description"],
                        exercise["color"],
                    )

                with c_mid:
                    st.markdown(
                        '<div style="display:flex;height:100%;min-height:160px;'
                        'align-items:center;justify-content:center;font-size:2rem;'
                        'color:#7fa8d6;font-weight:900;">→</div>',
                        unsafe_allow_html=True,
                    )

                with c2:
                    st.write("")
                    st.write("")
                    st.button(
                        "Commencer →",
                        key=exercise["key"],
                        use_container_width=True,
                        type="primary",
                        on_click=set_page,
                        args=(exercise["page"],),
                    )


EXERCISE1_STATES_WATER = [
    {
        "label": "Glacier",
        "answers": {"Solide"},
        "explanation": "Un glacier est constitué de glace : l’eau y est à l’état solide.",
    },
    {
        "label": "Pluie",
        "answers": {"Liquide"},
        "explanation": "Les gouttes de pluie sont de l’eau liquide.",
    },
    {
        "label": "Brouillard",
        "answers": {"Liquide"},
        "explanation": "Le brouillard est formé de minuscules gouttelettes d’eau liquide en suspension dans l’air.",
    },
    {
        "label": "Neige",
        "answers": {"Solide"},
        "explanation": "La neige est constituée de cristaux de glace : l’eau y est solide.",
    },
    {
        "label": "Atmosphère",
        "answers": {"Gazeux"},
        "explanation": "Dans l’atmosphère, l’eau peut être présente sous forme de vapeur d’eau, donc à l’état gazeux.",
    },
    {
        "label": "Vapeur d’eau",
        "answers": {"Gazeux"},
        "explanation": "La vapeur d’eau correspond à l’état gazeux de l’eau et elle est invisible.",
    },
    {
        "label": "Givre",
        "answers": {"Solide"},
        "explanation": "Le givre est constitué de cristaux de glace : c’est de l’eau solide.",
    },
    {
        "label": "Lacs",
        "answers": {"Liquide"},
        "explanation": "L’eau d’un lac est principalement à l’état liquide.",
    },
    {
        "label": "Nuage",
        "answers": {"Liquide", "Solide"},
        "explanation": "Un nuage peut contenir de minuscules gouttelettes d’eau liquide et des cristaux de glace.",
    },
    {
        "label": "Nappes phréatiques",
        "answers": {"Liquide"},
        "explanation": "L’eau des nappes phréatiques circule dans le sous-sol à l’état liquide.",
    },
    {
        "label": "Rivières et fleuves",
        "answers": {"Liquide"},
        "explanation": "L’eau des rivières et des fleuves est à l’état liquide.",
    },
]


def reset_exercise1_states_water():
    for key in list(st.session_state.keys()):
        if (
            str(key).startswith("ex1_water_")
            or str(key).startswith("ex1_click_")
        ):
            st.session_state.pop(key, None)
    st.session_state.pop("ex1_water_result_saved", None)
    st.session_state.pop("ex1_water_shuffled_order", None)

def ex1_hint_for_item(label):
    hints = {
        "Glacier": "Pense à la matière qui constitue un glacier : est-elle fluide ou rigide ?",
        "Pluie": "Observe une goutte de pluie : elle coule et prend la forme du récipient qui la reçoit.",
        "Brouillard": "Le brouillard est constitué de très petites gouttelettes en suspension dans l’air.",
        "Neige": "Les flocons sont formés de cristaux de glace.",
        "Atmosphère": "L’eau peut être présente dans l’air sous une forme invisible.",
        "Vapeur d’eau": "La vapeur d’eau est invisible et se diffuse dans l’air.",
        "Givre": "Le givre se forme sous forme de petits cristaux de glace.",
        "Lacs": "L’eau d’un lac peut s’écouler et prend la forme du bassin.",
        "Nuage": "Un nuage n’est pas uniquement constitué de vapeur d’eau invisible.",
        "Nappes phréatiques": "L’eau y circule entre les grains et les fissures du sous-sol.",
        "Rivières et fleuves": "Cette eau s’écoule et prend la forme de son lit.",
    }
    return hints.get(label, "Observe les propriétés de cette forme d’eau.")


def _ex1_cell_state(index, state_name):
    key = f"ex1_water_cell_{index}_{state_name}"
    return st.session_state.get(key, "idle")


def _ex1_handle_cell_click(index, state_name, correct_states):
    """Sélection neutre : aucune correction n'est révélée avant validation."""
    key = f"ex1_water_cell_{index}_{state_name}"
    current = st.session_state.get(key, "idle")
    st.session_state[key] = "selected" if current != "selected" else "idle"

    # Toute nouvelle modification invalide l'ancien feedback de la ligne.
    st.session_state.pop(f"ex1_water_row_feedback_{index}", None)
    st.session_state.pop(f"ex1_water_row_complete_{index}", None)


def _ex1_validate_row(index, correct_states):
    mapping = {
        "solid": "Solide",
        "liquid": "Liquide",
        "gas": "Gazeux",
    }

    selected = {
        human
        for state_name, human in mapping.items()
        if st.session_state.get(f"ex1_water_cell_{index}_{state_name}") == "selected"
    }

    if not selected:
        st.session_state[f"ex1_water_row_feedback_{index}"] = "empty"
        return

    if selected == set(correct_states):
        st.session_state[f"ex1_water_row_complete_{index}"] = True
        st.session_state[f"ex1_water_row_feedback_{index}"] = "correct"
    else:
        st.session_state[f"ex1_water_row_complete_{index}"] = False
        err_key = f"ex1_water_errors_{index}"
        st.session_state[err_key] = int(st.session_state.get(err_key, 0)) + 1
        st.session_state[f"ex1_water_row_feedback_{index}"] = "wrong"


def _ex1_render_answer_button(index, state_name, correct_states):
    state = _ex1_cell_state(index, state_name)

    state_label = {
        "solid": "Solide",
        "liquid": "Liquide",
        "gas": "Gazeux",
    }[state_name]

    selected = state == "selected"
    label = f"✓ {state_label}" if selected else state_label

    st.button(
        label,
        key=f"ex1_click_{index}_{state_name}",
        use_container_width=True,
        type="primary" if selected else "secondary",
        on_click=_ex1_handle_cell_click,
        args=(index, state_name, correct_states),
    )

    st.markdown(
        f'<div class="{"ex1-choice-selected" if selected else "ex1-choice-idle"}" '
        f'data-ex1="{index}-{state_name}"></div>',
        unsafe_allow_html=True,
    )


def _ex1_get_shuffled_order():
    """Create one random order per attempt and keep it stable during Streamlit reruns."""
    key = "ex1_water_shuffled_order"

    if key not in st.session_state:
        order = list(range(len(EXERCISE1_STATES_WATER)))
        random.shuffle(order)
        st.session_state[key] = order

    return st.session_state[key]



def _ex1_record_restart_if_needed():
    """Enregistre une tentative recommencée si l'élève avait déjà commencé l'exercice."""
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    total = len(EXERCISE1_STATES_WATER)
    touched = 0
    errors = 0

    for i in range(total):
        # Une ligne est considérée comme commencée si au moins un choix a été cliqué
        # ou si une erreur a déjà été comptabilisée.
        states = [
            st.session_state.get(f"ex1_water_cell_{i}_solid", "idle"),
            st.session_state.get(f"ex1_water_cell_{i}_liquid", "idle"),
            st.session_state.get(f"ex1_water_cell_{i}_gas", "idle"),
        ]
        if any(state != "idle" for state in states):
            touched += 1
        errors += int(st.session_state.get(f"ex1_water_errors_{i}", 0))

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == "exercise1_states_water"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise1_states_water",
        "resource_label": PILOT_CONTENTS.get("exercise1_states_water", {}).get("label", "Exercice 1"),
        "chapter": PILOT_CONTENTS.get("exercise1_states_water", {}).get("chapter", ""),
        "score_percent": None,
        "completed_items": touched,
        "total_items": total,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def _ex1_start_new_attempt():
    """Enregistre l'éventuelle tentative en cours, puis repart sur un nouvel ordre."""
    _ex1_record_restart_if_needed()
    reset_exercise1_states_water()

    order = list(range(len(EXERCISE1_STATES_WATER)))
    random.shuffle(order)
    st.session_state["ex1_water_shuffled_order"] = order

def page_exercise1_states_water():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise1_states_water"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex1-instruction {
            background: #f5f9ff;
            border: 1px solid #cfe0fb;
            border-radius: 16px;
            padding: .85rem 1rem;
            color: #324a68;
            margin: .35rem 0 .85rem 0;
        }

        .ex1-line-label {
            min-height: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            padding: 0 .85rem;
            background: #f1f3f6;
            border: 1px solid #dfe6ef;
            border-radius: 12px;
            color: #162b4d;
            font-weight: 800;
            font-size: .98rem;
            box-sizing: border-box;
        }

        .ex1-feedback-mini {
            min-height: 48px;
            height: 48px;
            display: flex;
            align-items: center;
            padding: 0 .75rem;
            border-radius: 12px;
            font-size: .9rem;
            font-weight: 700;
            box-sizing: border-box;
        }

        .ex1-feedback-empty {
            background: #f8fafc;
            border: 1px solid #e3e9f2;
            color: #90a0b3;
        }

        .ex1-feedback-ok {
            background: #eefaf2;
            border: 1px solid #cdebd6;
            color: #24623a;
        }

        .ex1-feedback-hint {
            background: #fff7e6;
            border: 1px solid #f4d69b;
            color: #73541c;
        }

        .ex1-feedback-correction {
            background: #fff1f1;
            border: 1px solid #f0c8c8;
            color: #7b2c2c;
        }

        /* Boutons des réponses compacts et alignés sur la ligne */
        div[data-testid="stButton"] button {
            min-height: 48px;
            height: 48px;
            font-weight: 800;
            border-radius: 12px;
            margin: 0 !important;
        }

        div[data-testid="stButton"] button[kind="secondary"] {
            background: #ffffff;
            border: 2px solid #cfd8e6;
            color: #18345d;
        }

        div[data-testid="stButton"] button[kind="primary"] {
            background: #2fb05b !important;
            border-color: #268f4b !important;
            color: #ffffff !important;
        }

        div[data-testid="stButton"]:has(+ .ex1-choice-idle) button {
            background: #ffffff !important;
            border-color: #cfd8e6 !important;
            color: #18345d !important;
        }

        div[data-testid="stButton"]:has(+ .ex1-choice-selected) button {
            background: #3478e5 !important;
            border-color: #2764c2 !important;
            color: #ffffff !important;
        }

        /* Réduit l'espace vertical entre les lignes */
        div[data-testid="stHorizontalBlock"] {
            gap: .6rem;
        }

        .ex1-line-spacer {
            height: .35rem;
        }

        @media (max-width: 900px) {
            .ex1-feedback-mini {
                font-size: .82rem;
                padding: 0 .55rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Identifier les états de l’eau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">💧 Exercice 1 — Identifier les états de l’eau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ex1-instruction">
            <strong>ℹ️ Consigne :</strong> Pour chaque proposition, clique sur l’état ou les états physiques correspondants.
            La correction apparaît immédiatement.
        </div>
        """,
        unsafe_allow_html=True,
    )

    shuffled_order = _ex1_get_shuffled_order()

    for index in shuffled_order:
        item = EXERCISE1_STATES_WATER[index]
        # Proposition + 3 choix + validation + feedback, sur UNE seule ligne.
        c1, c2, c3, c4, c5, c6 = st.columns([2.0, 1.0, 1.0, 1.0, 1.0, 2.4], gap="small")

        with c1:
            st.markdown(
                f'<div class="ex1-line-label">{item["label"]}</div>',
                unsafe_allow_html=True,
            )

        with c2:
            _ex1_render_answer_button(index, "solid", item["answers"])

        with c3:
            _ex1_render_answer_button(index, "liquid", item["answers"])

        with c4:
            _ex1_render_answer_button(index, "gas", item["answers"])

        with c5:
            st.button(
                "Valider",
                key=f"ex1_validate_row_{index}",
                use_container_width=True,
                on_click=_ex1_validate_row,
                args=(index, item["answers"]),
            )

        error_count = int(st.session_state.get(f"ex1_water_errors_{index}", 0))
        row_complete = bool(st.session_state.get(f"ex1_water_row_complete_{index}", False))
        row_feedback = st.session_state.get(f"ex1_water_row_feedback_{index}")

        with c6:
            if row_complete:
                feedback_html = (
                    f'<div class="ex1-feedback-mini ex1-feedback-ok">'
                    f'✅ {item["label"]} : bonne réponse.</div>'
                )
            elif row_feedback == "empty":
                feedback_html = (
                    '<div class="ex1-feedback-mini ex1-feedback-hint">'
                    'Choisis au moins une réponse.</div>'
                )
            elif error_count == 1:
                feedback_html = (
                    f'<div class="ex1-feedback-mini ex1-feedback-hint">'
                    f'💡 {ex1_hint_for_item(item["label"])}</div>'
                )
            elif error_count >= 2:
                correct_text = " + ".join(sorted(item["answers"]))
                feedback_html = (
                    f'<div class="ex1-feedback-mini ex1-feedback-correction">'
                    f'❌ {correct_text} — {item["explanation"]}</div>'
                )
            else:
                feedback_html = (
                    '<div class="ex1-feedback-mini ex1-feedback-empty">'
                    'Correction</div>'
                )

            st.markdown(feedback_html, unsafe_allow_html=True)

        st.markdown('<div class="ex1-line-spacer"></div>', unsafe_allow_html=True)

    reset_col, spacer = st.columns([1.3, 4.7])
    with reset_col:
        if st.button(
            "↻ Recommencer",
            use_container_width=True,
            key="restart_ex1_states_water",
        ):
            _ex1_start_new_attempt()
            st.rerun()

    total = len(EXERCISE1_STATES_WATER)
    complete_rows = sum(
        1
        for i in range(total)
        if st.session_state.get(f"ex1_water_row_complete_{i}", False)
    )

    if complete_rows:
        st.markdown("### Ton avancement")
        st.progress(complete_rows / total)
        st.write(f"**{complete_rows} / {total} propositions réussies**")

        if complete_rows == total:
            st.success("🎉 Bravo ! Toutes tes réponses sont correctes.")

            student = st.session_state.get("app_student")
            if (
                st.session_state.get("app_user_type") == "student"
                and student
                and not st.session_state.get("ex1_water_result_saved", False)
            ):
                total_errors = sum(
                    int(st.session_state.get(f"ex1_water_errors_{i}", 0))
                    for i in range(total)
                )

                mastery_score = round(
                    100 * total / max(total, total + total_errors)
                )

                record_training_result(
                    student,
                    "exercise1_states_water",
                    mastery_score,
                    total,
                    total,
                    errors=total_errors,
                )
                st.session_state["ex1_water_result_saved"] = True


# ============================================================
# EXERCICE 2 — PARTICULARITÉS DES ÉTATS DE L'EAU
# ============================================================

EXERCISE2_WATER_IMAGES = {
    "ice": {
        "path": "assets/chapitre_1/exercice_2/Glace.png",
        "alt": "Glaçon",
    },
    "liquid": {
        "path": "assets/chapitre_1/exercice_2/liquide.png",
        "alt": "Goutte d’eau",
    },
    "vapor": {
        "path": "assets/chapitre_1/exercice_2/vapeur.png",
        "alt": "Vapeur d’eau",
    },
}

EXERCISE2_LABELS = [
    {
        "label": "liquide",
        "target": "liquid",
        "hint": "Cherche l’image qui représente de l’eau pouvant s’écouler.",
        "explanation": "L’eau liquide correspond ici à la goutte d’eau.",
    },
    {
        "label": "solide",
        "target": "ice",
        "hint": "Cherche l’image dont la forme reste propre et rigide.",
        "explanation": "La glace est de l’eau à l’état solide.",
    },
    {
        "label": "glace",
        "target": "ice",
        "hint": "Le nom usuel recherché correspond à l’eau gelée.",
        "explanation": "Le glaçon représente la glace.",
    },
    {
        "label": "gaz",
        "target": "vapor",
        "hint": "Cherche la représentation correspondant à l’état gazeux.",
        "explanation": "La vapeur d’eau correspond à l’état gazeux de l’eau.",
    },
    {
        "label": "coule",
        "target": "liquid",
        "hint": "Cette propriété caractérise l’eau qui peut s’écouler.",
        "explanation": "L’eau liquide coule.",
    },
    {
        "label": "vapeur",
        "target": "vapor",
        "hint": "Cherche la représentation de l’eau à l’état gazeux.",
        "explanation": "La vapeur d’eau est le nom usuel de l’eau à l’état gazeux.",
    },
    {
        "label": "peut être saisi avec les doigts",
        "target": "ice",
        "hint": "Quel état permet de prendre directement l’objet dans la main ?",
        "explanation": "Un glaçon est solide : il peut être saisi avec les doigts.",
    },
    {
        "label": "eau",
        "target": "liquid",
        "hint": "Ici, le mot désigne l’eau liquide représentée par la goutte.",
        "explanation": "Dans cet exercice, « eau » correspond à l’image de l’eau liquide.",
    },
    {
        "label": "souvent invisible",
        "target": "vapor",
        "hint": "L’eau à l’état gazeux n’est généralement pas visible à l’œil nu.",
        "explanation": "La vapeur d’eau est généralement invisible.",
    },
]


def _ex2_get_image_order():
    """Les lettres A, B, C restent fixes ; seules les images changent de place."""
    key = "ex2_image_order"
    if key not in st.session_state:
        order = list(EXERCISE2_WATER_IMAGES.keys())
        random.shuffle(order)
        st.session_state[key] = order
    return st.session_state[key]


def _ex2_letter_for_target(target):
    order = _ex2_get_image_order()
    letters = ["A", "B", "C"]
    return letters[order.index(target)]


def _ex2_choice_state(index, letter):
    return st.session_state.get(f"ex2_choice_{index}_{letter}", "idle")


def _ex2_answer_click(index, letter, correct_letter):
    """Correction immédiate au clic sur A, B ou C."""
    if letter == correct_letter:
        st.session_state[f"ex2_choice_{index}_{letter}"] = "correct"
        st.session_state[f"ex2_item_complete_{index}"] = True
    else:
        st.session_state[f"ex2_choice_{index}_{letter}"] = "wrong"
        err_key = f"ex2_errors_{index}"
        st.session_state[err_key] = int(st.session_state.get(err_key, 0)) + 1


def _ex2_render_letter_button(index, letter, correct_letter):
    state = _ex2_choice_state(index, letter)

    if state == "correct":
        label = f"✓ {letter}"
        button_type = "primary"
    elif state == "wrong":
        label = f"✕ {letter}"
        button_type = "secondary"
    else:
        label = letter
        button_type = "secondary"

    st.button(
        label,
        key=f"ex2_btn_{index}_{letter}",
        use_container_width=True,
        type=button_type,
        on_click=_ex2_answer_click,
        args=(index, letter, correct_letter),
    )

    state_class = {
        "idle": "ex2-choice-idle",
        "correct": "ex2-choice-correct",
        "wrong": "ex2-choice-wrong",
    }[state]
    st.markdown(
        f'<div class="{state_class}" data-ex2="{index}-{letter}"></div>',
        unsafe_allow_html=True,
    )


def _ex2_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    touched = 0
    errors = 0
    total = len(EXERCISE2_LABELS)

    for i in range(total):
        if any(
            st.session_state.get(f"ex2_choice_{i}_{letter}", "idle") != "idle"
            for letter in ("A", "B", "C")
        ):
            touched += 1
        errors += int(st.session_state.get(f"ex2_errors_{i}", 0))

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == "exercise2_water_properties"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise2_water_properties",
        "resource_label": PILOT_CONTENTS["exercise2_water_properties"]["label"],
        "chapter": PILOT_CONTENTS["exercise2_water_properties"]["chapter"],
        "score_percent": None,
        "completed_items": touched,
        "total_items": total,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise2_water_properties():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex2_"):
            st.session_state.pop(key, None)


def _ex2_start_new_attempt():
    _ex2_record_restart_if_needed()
    reset_exercise2_water_properties()
    order = list(EXERCISE2_WATER_IMAGES.keys())
    random.shuffle(order)
    st.session_state["ex2_image_order"] = order


def page_exercise2_water_properties():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise2_water_properties"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex2-instruction {
            background: #f5f9ff;
            border: 1px solid #cfe0fb;
            border-radius: 16px;
            padding: .85rem 1rem;
            color: #324a68;
            margin: .35rem 0 .9rem 0;
        }

        .ex2-letter {
            width: 42px;
            height: 42px;
            margin: 0 auto .45rem auto;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            background: #173b70;
            color: white;
            font-weight: 900;
            font-size: 1.15rem;
        }

        .ex2-image-card {
            background: #f4f6f9;
            border: 1px solid #dfe6ef;
            border-radius: 16px;
            padding: .75rem;
            text-align: center;
            min-height: 270px;
        }

        .ex2-fixed-image-wrap {
            height: 245px;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto .4rem auto;
            overflow: hidden;
        }

        .ex2-fixed-image-wrap img {
            width: 220px;
            height: 220px;
            object-fit: contain;
            display: block;
        }

        .ex2-label {
            min-height: 46px;
            height: 46px;
            display: flex;
            align-items: center;
            padding: 0 .8rem;
            border-radius: 11px;
            background: #f1f3f6;
            border: 1px solid #dfe6ef;
            font-weight: 800;
            color: #162b4d;
            box-sizing: border-box;
        }

        .ex2-feedback {
            min-height: 46px;
            height: 46px;
            display: flex;
            align-items: center;
            padding: 0 .7rem;
            border-radius: 11px;
            font-size: .88rem;
            font-weight: 700;
            box-sizing: border-box;
        }

        .ex2-feedback-empty {
            background: #f8fafc;
            border: 1px solid #e3e9f2;
            color: #92a0b2;
        }

        .ex2-feedback-ok {
            background: #eefaf2;
            border: 1px solid #cdebd6;
            color: #24623a;
        }

        .ex2-feedback-hint {
            background: #fff7e6;
            border: 1px solid #f4d69b;
            color: #73541c;
        }

        .ex2-feedback-correction {
            background: #fff1f1;
            border: 1px solid #f0c8c8;
            color: #7b2c2c;
        }

        div[data-testid="stButton"]:has(+ .ex2-choice-wrong) button {
            background: #e05656 !important;
            border-color: #bd3d3d !important;
            color: #ffffff !important;
        }

        div[data-testid="stButton"]:has(+ .ex2-choice-idle) button {
            background: #ffffff !important;
            border: 2px solid #cfd8e6 !important;
            color: #18345d !important;
        }

        div[data-testid="stButton"]:has(+ .ex2-choice-correct) button {
            background: #2fb05b !important;
            border-color: #268f4b !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Particularités des états de l’eau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">🧊 Exercice 2 — Les particularités des états de l’eau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ex2-instruction">
            <strong>ℹ️ Consigne :</strong> Observe les trois images A, B et C.
            Pour chaque étiquette, clique sur la lettre de l’image correspondante.
            Les lettres restent dans l’ordre A–B–C, mais les images changent de place à chaque nouvelle tentative.
        </div>
        """,
        unsafe_allow_html=True,
    )

    order = _ex2_get_image_order()
    letters = ["A", "B", "C"]
    cols = st.columns(3, gap="medium")

    missing_assets = []

    for col, letter, image_key in zip(cols, letters, order):
        info = EXERCISE2_WATER_IMAGES[image_key]
        with col:
            st.markdown(f'<div class="ex2-letter">{letter}</div>', unsafe_allow_html=True)
            path = Path(info["path"])
            if path.exists():
                import base64
                mime = "image/png"
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                st.markdown(
                    f"""
                    <div class="ex2-fixed-image-wrap">
                        <img src="data:{mime};base64,{encoded}" alt="{info['alt']}">
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                missing_assets.append(info["path"])
                st.warning(f"Image manquante : {path.name}")

    if missing_assets:
        st.info(
            "Ajoute les images dans assets/chapitre_1/exercice_2/ : Glace.png, liquide.png et vapeur.png."
        )

    st.markdown("### Associe chaque étiquette")

    for index, item in enumerate(EXERCISE2_LABELS):
        correct_letter = _ex2_letter_for_target(item["target"])

        c1, c2, c3, c4, c5 = st.columns([2.8, .75, .75, .75, 2.8], gap="small")

        with c1:
            st.markdown(
                f'<div class="ex2-label">{item["label"]}</div>',
                unsafe_allow_html=True,
            )

        with c2:
            _ex2_render_letter_button(index, "A", correct_letter)
        with c3:
            _ex2_render_letter_button(index, "B", correct_letter)
        with c4:
            _ex2_render_letter_button(index, "C", correct_letter)

        error_count = int(st.session_state.get(f"ex2_errors_{index}", 0))
        complete = bool(st.session_state.get(f"ex2_item_complete_{index}", False))

        with c5:
            if complete:
                feedback = (
                    f'<div class="ex2-feedback ex2-feedback-ok">'
                    f'✅ Bonne réponse : {correct_letter}</div>'
                )
            elif error_count == 1:
                feedback = (
                    f'<div class="ex2-feedback ex2-feedback-hint">'
                    f'💡 {item["hint"]}</div>'
                )
            elif error_count >= 2:
                feedback = (
                    f'<div class="ex2-feedback ex2-feedback-correction">'
                    f'❌ Lettre {correct_letter} — {item["explanation"]}</div>'
                )
            else:
                feedback = (
                    '<div class="ex2-feedback ex2-feedback-empty">Correction</div>'
                )

            st.markdown(feedback, unsafe_allow_html=True)

    total = len(EXERCISE2_LABELS)
    completed = sum(
        1 for i in range(total)
        if st.session_state.get(f"ex2_item_complete_{i}", False)
    )

    c_reset, c_space = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            use_container_width=True,
            key="restart_ex2_water_properties",
        ):
            _ex2_start_new_attempt()
            st.rerun()

    if completed:
        st.markdown("### Ton avancement")
        st.progress(completed / total)
        st.write(f"**{completed} / {total} étiquettes correctement associées**")

    if completed == total:
        st.success("🎉 Bravo ! Toutes les associations sont correctes.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex2_result_saved", False)
        ):
            total_errors = sum(
                int(st.session_state.get(f"ex2_errors_{i}", 0))
                for i in range(total)
            )

            mastery_score = round(
                100 * total / max(total, total + total_errors)
            )

            record_training_result(
                student,
                "exercise2_water_properties",
                mastery_score,
                total,
                total,
                errors=total_errors,
            )
            st.session_state["ex2_result_saved"] = True



# ============================================================
# EXERCICE 3 — COMPRENDRE LA MODÉLISATION
# ============================================================

EXERCISE3_MODELS = {
    "solid": {
        "path": "assets/chapitre_1/exercice 3/bouteille eau solide.png",
        "answer": "solide",
        "alt": "Modèle particulaire d'un solide",
    },
    "liquid": {
        "path": "assets/chapitre_1/exercice 3/bouteille eau liquide.png",
        "answer": "liquide",
        "alt": "Modèle particulaire d'un liquide",
    },
    "gas": {
        "path": "assets/chapitre_1/exercice 3/bouteille eau gazeuse.png",
        "answer": "gaz",
        "alt": "Modèle particulaire d'un gaz",
    },
}

EXERCISE3_COURSE_HELP = "assets/chapitre_1/exercice 3/aide cours.png"


def _normalize_state_answer(value):
    value = str(value or "").strip().lower()
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)

    value = " ".join(value.split())

    aliases = {
        "solide": "solide",
        "etat solide": "solide",
        "liquide": "liquide",
        "etat liquide": "liquide",
        "gaz": "gaz",
        "gazeux": "gaz",
        "etat gazeux": "gaz",
        "etat gaz": "gaz",
    }
    return aliases.get(value, value)


def _ex3_get_order():
    key = "ex3_model_order"
    if key not in st.session_state:
        order = list(EXERCISE3_MODELS.keys())
        random.shuffle(order)
        st.session_state[key] = order
    return st.session_state[key]



def _ex3_specific_feedback(raw_value):
    """Retour ciblé pour quelques confusions fréquentes, sans révéler la bonne réponse."""
    value = _normalize_state_answer(raw_value)

    if value == "eau":
        return (
            "❌ « Eau » désigne une matière, pas un état physique. "
            "On te demande ici d’identifier un état de la matière."
        )

    if value in {"glace", "glacon", "glaçon"}:
        return (
            "❌ « Glace » n’est pas le nom attendu ici. "
            "Cherche le nom de l’état physique correspondant."
        )

    if value in {"vapeur", "vapeur d'eau", "vapeur d’eau"}:
        return (
            "❌ « Vapeur d’eau » n’est pas le nom attendu ici. "
            "Cherche le nom de l’état physique correspondant."
        )

    return None


def _ex3_validate_model(model_key):
    generation = int(st.session_state.get("ex3_generation", 0))
    answer_key = f"ex3_answer_{generation}_{model_key}"
    errors_key = f"ex3_errors_{model_key}"
    correct_key = f"ex3_correct_{model_key}"
    feedback_key = f"ex3_specific_feedback_{model_key}"

    raw_value = st.session_state.get(answer_key, "")
    given = _normalize_state_answer(raw_value)
    expected = EXERCISE3_MODELS[model_key]["answer"]

    if not given:
        st.session_state[f"ex3_empty_{model_key}"] = True
        st.session_state.pop(feedback_key, None)
        return

    st.session_state[f"ex3_empty_{model_key}"] = False

    if given == expected:
        st.session_state[correct_key] = True
        st.session_state.pop(feedback_key, None)
    else:
        st.session_state[correct_key] = False
        st.session_state[errors_key] = int(st.session_state.get(errors_key, 0)) + 1

        specific = _ex3_specific_feedback(raw_value)
        if specific:
            st.session_state[feedback_key] = specific
        else:
            st.session_state.pop(feedback_key, None)


def _ex3_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    touched = 0
    errors = 0
    total = len(EXERCISE3_MODELS)

    generation = int(st.session_state.get("ex3_generation", 0))

    for model_key in EXERCISE3_MODELS:
        if str(st.session_state.get(f"ex3_answer_{generation}_{model_key}", "")).strip():
            touched += 1
        errors += int(st.session_state.get(f"ex3_errors_{model_key}", 0))

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == "exercise3_particle_models"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise3_particle_models",
        "resource_label": PILOT_CONTENTS["exercise3_particle_models"]["label"],
        "chapter": PILOT_CONTENTS["exercise3_particle_models"]["chapter"],
        "score_percent": None,
        "completed_items": touched,
        "total_items": total,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise3_particle_models():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex3_"):
            st.session_state.pop(key, None)


def _ex3_start_new_attempt():
    _ex3_record_restart_if_needed()

    current_generation = int(st.session_state.get("ex3_generation", 0))
    reset_exercise3_particle_models()

    # Une nouvelle clé de widget est créée à chaque tentative :
    # les champs de saisie repartent donc réellement vides.
    st.session_state["ex3_generation"] = current_generation + 1

    order = list(EXERCISE3_MODELS.keys())
    random.shuffle(order)
    st.session_state["ex3_model_order"] = order


def page_exercise3_particle_models():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise3_particle_models"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex3-instruction {
            background: #f5f9ff;
            border: 1px solid #cfe0fb;
            border-radius: 16px;
            padding: .85rem 1rem;
            color: #324a68;
            margin: .35rem 0 .8rem 0;
        }

        .ex3-legend {
            background: #eefaf7;
            border: 1px solid #c8e8df;
            border-radius: 13px;
            padding: .7rem .9rem;
            color: #285b50;
            font-weight: 700;
            margin-bottom: .9rem;
        }

        .ex3-help-1 {
            background: #fff7e6;
            border: 1px solid #f4d69b;
            border-radius: 12px;
            padding: .65rem .8rem;
            color: #73541c;
            margin-top: .4rem;
        }

        .ex3-help-2 {
            background: #eef6ff;
            border: 1px solid #cfe0fb;
            border-radius: 12px;
            padding: .7rem .85rem;
            color: #284e7a;
            margin-top: .4rem;
        }

        .ex3-help-3 {
            background: #f6f1ff;
            border: 1px solid #d9c9f4;
            border-radius: 12px;
            padding: .65rem .8rem;
            color: #563b7c;
            margin-top: .4rem;
        }

        .ex3-correct {
            background: #eefaf2;
            border: 1px solid #cdebd6;
            border-radius: 12px;
            padding: .65rem .8rem;
            color: #24623a;
            margin-top: .4rem;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Comprendre la modélisation</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">🔬 Exercice 3 — Comprendre la modélisation</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ex3-instruction">
            <strong>ℹ️ Consigne :</strong> Observe chaque modèle et écris l’état de la matière représenté.
            Aucune proposition n’est donnée au départ : à toi de raisonner à partir du modèle.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ex3-legend">
            🟢 <strong>Légende :</strong> chaque pastille turquoise représente une molécule de matière.
        </div>
        """,
        unsafe_allow_html=True,
    )

    order = _ex3_get_order()
    cols = st.columns(3, gap="large")

    missing = []

    for col, model_key in zip(cols, order):
        info = EXERCISE3_MODELS[model_key]

        with col:
            path = Path(info["path"])
            if path.exists():
                st.image(str(path), width=250)
            else:
                missing.append(info["path"])
                st.warning(f"Image manquante : {path.name}")

            generation = int(st.session_state.get("ex3_generation", 0))

            st.text_input(
                "Quel état de la matière est représenté ?",
                key=f"ex3_answer_{generation}_{model_key}",
                placeholder="Écris ta réponse puis appuie sur Entrée",
                disabled=bool(st.session_state.get(f"ex3_correct_{model_key}", False)),
                on_change=_ex3_validate_model,
                args=(model_key,),
            )

            st.button(
                "Vérifier",
                key=f"ex3_validate_{model_key}",
                use_container_width=True,
                on_click=_ex3_validate_model,
                args=(model_key,),
                disabled=bool(st.session_state.get(f"ex3_correct_{model_key}", False)),
            )

            if st.session_state.get(f"ex3_empty_{model_key}", False):
                st.warning("Écris d’abord une réponse.")

            errors = int(st.session_state.get(f"ex3_errors_{model_key}", 0))
            correct = bool(st.session_state.get(f"ex3_correct_{model_key}", False))
            specific_feedback = st.session_state.get(f"ex3_specific_feedback_{model_key}")

            if correct:
                st.markdown(
                    f'<div class="ex3-correct">✅ Bonne réponse : <strong>{info["answer"]}</strong>.</div>',
                    unsafe_allow_html=True,
                )

            elif errors == 1:
                if specific_feedback:
                    st.markdown(
                        f'<div class="ex3-help-1">{specific_feedback}</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    """
                    <div class="ex3-help-1">
                        💡 <strong>Premier indice :</strong> observe bien la <strong>disposition des molécules</strong>.
                        Sont-elles proches les unes des autres ou très espacées ?
                        Lorsqu’elles sont proches, semblent-elles rangées ou désordonnées ?
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            elif errors == 2:
                if specific_feedback:
                    st.markdown(
                        f'<div class="ex3-help-1">{specific_feedback}</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    """
                    <div class="ex3-help-2">
                        📘 <strong>Rappel du cours :</strong><br>
                        • <strong>Solide</strong> : molécules compactes et ordonnées.<br>
                        • <strong>Liquide</strong> : molécules compactes et désordonnées.<br>
                        • <strong>Gaz</strong> : molécules dispersées et désordonnées.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            elif errors >= 3:
                if specific_feedback:
                    st.markdown(
                        f'<div class="ex3-help-1">{specific_feedback}</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    """
                    <div class="ex3-help-3">
                        🔎 <strong>Aide complète :</strong> compare maintenant ton modèle avec les schémas du cours ci-dessous.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if missing:
        st.info(
            "Les trois images doivent être placées dans "
            "assets/chapitre_1/exercice 3/ avec les noms : "
            "bouteille eau solide.png, bouteille eau liquide.png et bouteille eau gazeuse.png."
        )

    # Aide visuelle commune :
    # elle apparaît seulement tant qu'au moins une réponse ayant atteint
    # le 3e niveau d'aide reste incorrecte. Dès que cette réponse est corrigée,
    # l'aide disparaît automatiquement.
    models_needing_visual_help = [
        key
        for key in EXERCISE3_MODELS
        if (
            int(st.session_state.get(f"ex3_errors_{key}", 0)) >= 3
            and not bool(st.session_state.get(f"ex3_correct_{key}", False))
        )
    ]

    if models_needing_visual_help:
        help_path = Path(EXERCISE3_COURSE_HELP)
        st.markdown("### Aide visuelle du cours")
        if help_path.exists():
            st.image(str(help_path), use_container_width=True)
        else:
            st.warning(
                "Image d’aide manquante : ajoute « aide cours.png » dans "
                "assets/chapitre_1/exercice 3/."
            )

    total = len(EXERCISE3_MODELS)
    completed = sum(
        1 for key in EXERCISE3_MODELS
        if st.session_state.get(f"ex3_correct_{key}", False)
    )

    c_reset, c_space = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            use_container_width=True,
            key="restart_ex3_particle_models",
        ):
            _ex3_start_new_attempt()
            st.rerun()

    if completed:
        st.markdown("### Ton avancement")
        st.progress(completed / total)
        st.write(f"**{completed} / {total} modèles correctement identifiés**")

    if completed == total:
        st.success("🎉 Bravo ! Tu as correctement identifié les trois états de la matière.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex3_result_saved", False)
        ):
            total_errors = sum(
                int(st.session_state.get(f"ex3_errors_{key}", 0))
                for key in EXERCISE3_MODELS
            )

            mastery_score = round(
                100 * total / max(total, total + total_errors)
            )

            record_training_result(
                student,
                "exercise3_particle_models",
                mastery_score,
                total,
                total,
                errors=total_errors,
            )
            st.session_state["ex3_result_saved"] = True




# ============================================================
# MODULE INTERACTIF — MODÉLISATION PAR GLISSER-DÉPOSER
# ============================================================

EX4_DRAGDROP_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{
    --navy:#173b70;
    --teal:#15d7b2;
    --teal2:#0da98f;
    --teal-dark:#075e64;
    --pale:#f5f9ff;
    --line:#cfdbea;
    --good:#eaf8ef;
    --good-line:#b8e2c4;
    --hint:#fff8e8;
    --hint-line:#efd89c;
  }
  *{box-sizing:border-box}
  body{
    margin:0;
    font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
    color:#17345f;
    background:#fff;
  }
  .wrap{max-width:1100px;margin:0 auto;padding:8px 10px 14px}
  .intro{
    background:var(--pale);
    border:1px solid #cfe0fb;
    border-radius:14px;
    padding:11px 14px;
    margin-bottom:12px;
    font-size:14px;
    line-height:1.45;
  }
  .layout{
    display:grid;
    grid-template-columns:220px 1fr 220px;
    gap:16px;
    align-items:start;
  }
  .tray{
    background:#f7f9fc;
    border:1px solid var(--line);
    border-radius:16px;
    padding:12px;
    min-height:220px;
  }
  .tray h4{margin:0 0 6px;text-align:center;font-size:14px}
  .tray p{margin:0 0 12px;text-align:center;color:#63738a;font-size:12px}
  .pool{
    display:flex;
    flex-wrap:wrap;
    justify-content:center;
    gap:9px;
    min-height:130px;
    align-content:flex-start;
  }

  .mol{
    width:32px;
    height:32px;
    border-radius:50%;
    background:
      radial-gradient(circle at 31% 28%,
      #9affeb 0 16%, var(--teal) 18% 63%, var(--teal2) 65% 100%);
    border:3px solid var(--teal-dark);
    box-shadow:0 2px 6px rgba(0,0,0,.16);
    cursor:grab;
    touch-action:none;
    user-select:none;
    -webkit-user-select:none;
    -webkit-touch-callout:none;
  }
  .source-mol{position:relative;flex:0 0 auto}
  .placed-mol{
    position:absolute;
    display:none;
    z-index:30;
  }
  .ghost{
    position:fixed !important;
    z-index:99999 !important;
    pointer-events:none !important;
    transform:scale(1.08);
    box-shadow:0 5px 12px rgba(0,0,0,.28);
  }

  .center{min-width:0}
  .stage{position:relative;height:560px;max-width:510px;margin:0 auto}
  .bottle{position:absolute;inset:0;margin:auto;width:360px;height:530px}
  .neck{
    position:absolute;width:126px;height:76px;left:117px;top:4px;
    border:5px solid #172027;border-bottom:none;
    border-radius:16px 16px 0 0;background:rgba(255,255,255,.9)
  }
  .valve{
    position:absolute;width:76px;height:18px;left:142px;top:-5px;
    border:4px solid #172027;border-radius:4px;background:#fff
  }
  .bottle-body{
    position:absolute;
    left:28px;top:66px;width:304px;height:450px;
    border:5px solid #172027;
    border-radius:76px 76px 54px 54px;
    background:linear-gradient(90deg,#ecfffbcc,#fff,#e9fcf9cc);
    overflow:hidden;
  }
  .divider{
    position:absolute;left:0;right:0;top:304px;height:4px;
    background:#172027;z-index:5;pointer-events:none
  }
  .zone-overlay{
    position:absolute;left:0;right:0;
    pointer-events:none;
    transition:background .12s ease;
  }
  #zoneA{top:0;height:304px}
  #zoneB{top:308px;height:142px}
  .zone-overlay.active{background:rgba(21,215,178,.10)}
  .zone-label{
    position:absolute;right:10px;z-index:6;
    font-size:13px;font-weight:800;color:var(--navy);
    background:#fffffff0;border:1px solid #cfdbea;
    border-radius:999px;padding:4px 9px;pointer-events:none
  }
  .label-a{top:12px}.label-b{top:320px}

  .legend{
    display:flex;align-items:center;justify-content:center;gap:8px;
    margin-top:4px;font-size:12px;color:#5e6f85
  }
  .legend-dot{
    width:18px;height:18px;border-radius:50%;
    background:var(--teal);border:2px solid var(--teal-dark)
  }
  .controls{
    display:flex;justify-content:center;gap:10px;
    margin:12px 0 8px;flex-wrap:wrap
  }
  button{
    border:1px solid #bfcde0;border-radius:11px;padding:9px 15px;
    font-weight:750;background:#fff;color:#17345f;cursor:pointer
  }
  button.primary{background:#1f6fd6;border-color:#1b61b9;color:#fff}
  .feedback{
    display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px
  }
  .msg{
    min-height:52px;display:flex;align-items:center;border-radius:12px;
    padding:10px 12px;font-size:13px;font-weight:650
  }
  .neutral{background:#f7f9fc;border:1px solid #dfe6ef;color:#6e7c90}
  .good{background:var(--good);border:1px solid var(--good-line);color:#24623a}
  .hint{background:var(--hint);border:1px solid var(--hint-line);color:#73541c}

  @media(max-width:900px){
    .layout{grid-template-columns:1fr}
    .tray{min-height:0}
    .pool{min-height:72px}
    .stage{height:540px}
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="intro">
    <strong>Modélise le contenu de la bouteille.</strong>
    Fais glisser les 8 molécules de la zone <strong>a</strong> dans la partie supérieure
    et les 8 molécules de la zone <strong>b</strong> dans la partie inférieure.
    Une fois placées, tu peux reprendre chaque molécule et la déplacer librement
    dans son compartiment.
  </div>

  <div class="layout">
    <div class="tray">
      <h4>Molécules pour la zone a</h4>
      <p>8 molécules à placer</p>
      <div class="pool" id="poolA"></div>
    </div>

    <div class="center">
      <div class="stage">
        <div class="bottle">
          <div class="valve"></div>
          <div class="neck"></div>
          <div class="bottle-body" id="bottleBody">
            <div class="zone-overlay" id="zoneA"></div>
            <div class="divider"></div>
            <div class="zone-overlay" id="zoneB"></div>
            <div class="zone-label label-a">zone a</div>
            <div class="zone-label label-b">zone b</div>
          </div>
        </div>
      </div>
      <div class="legend">
        <span class="legend-dot"></span>
        Chaque pastille représente une molécule de dioxygène.
      </div>
    </div>

    <div class="tray">
      <h4>Molécules pour la zone b</h4>
      <p>8 molécules à placer</p>
      <div class="pool" id="poolB"></div>
    </div>
  </div>

  <div style="text-align:center;color:#9aa7b8;font-size:10px;margin-top:4px;">module interactif v31</div>
  <div class="controls">
    <button id="resetA">↻ Remettre les molécules de A</button>
    <button id="resetB">↻ Remettre les molécules de B</button>
    <button id="resetAll">↻ Remettre A et B</button>
    <button class="primary" id="check">Vérifier mon modèle</button>
  </div>

  <div class="feedback">
    <div id="feedbackA" class="msg neutral">Zone a : modèle non vérifié.</div>
    <div id="feedbackB" class="msg neutral">Zone b : modèle non vérifié.</div>
  </div>
</div>

<script>
(function(){
  const N = 8;
  const DIVIDER_Y = 304;

  let generation = null;
  let storageId = "default";
  let initialized = false;
  let drag = null;

  let state = freshState();

  function freshState(){
    return {
      a:Array(N).fill(null),
      b:Array(N).fill(null),
      errors:{a:0,b:0},
      success:{a:false,b:false}
    };
  }

  function storageKey(){
    return "ludo_ex4_dragdrop_v31_" + storageId + "_" + String(generation ?? 0);
  }

  function saveLocal(){
    try{
      sessionStorage.setItem(storageKey(), JSON.stringify(state));
    }catch(e){}
  }

  function loadLocal(){
    try{
      const raw=sessionStorage.getItem(storageKey());
      if(!raw) return freshState();
      const parsed=JSON.parse(raw);
      if(!parsed.a || !parsed.b) return freshState();
      return {
        a:Array.from({length:N},(_,i)=>parsed.a[i] ?? null),
        b:Array.from({length:N},(_,i)=>parsed.b[i] ?? null),
        errors:{
          a:Number(parsed.errors?.a || 0),
          b:Number(parsed.errors?.b || 0)
        },
        success:{
          a:Boolean(parsed.success?.a),
          b:Boolean(parsed.success?.b)
        }
      };
    }catch(e){
      return freshState();
    }
  }

  function sendReady(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:componentReady",
      apiVersion:1
    },"*");
  }

  function setHeight(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setFrameHeight",
      height:document.documentElement.scrollHeight + 8
    },"*");
  }

  function sendValue(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setComponentValue",
      value:{
        zone_a:state.success.a,
        zone_b:state.success.b,
        errors_a:state.errors.a,
        errors_b:state.errors.b,
        positions:{
          a:state.a.filter(Boolean),
          b:state.b.filter(Boolean)
        }
      }
    },"*");
  }

  function sourceId(group,index){return `source-${group}-${index}`}
  function placedId(group,index){return `placed-${group}-${index}`}

  function makeSource(group,index){
    const e=document.createElement("div");
    e.className="mol source-mol";
    e.id=sourceId(group,index);
    e.dataset.group=group;
    e.dataset.index=String(index);
    e.setAttribute("role","button");
    e.setAttribute("aria-label",`Molécule ${index+1}, zone ${group}`);
    e.addEventListener("pointerdown",startDrag);
    return e;
  }

  function makePlaced(group,index){
    const e=document.createElement("div");
    e.className="mol placed-mol";
    e.id=placedId(group,index);
    e.dataset.group=group;
    e.dataset.index=String(index);
    e.setAttribute("role","button");
    e.setAttribute("aria-label",`Molécule placée ${index+1}, zone ${group}`);
    e.addEventListener("pointerdown",startDrag);
    return e;
  }

  function sourceEl(group,index){
    return document.getElementById(sourceId(group,index));
  }
  function placedEl(group,index){
    return document.getElementById(placedId(group,index));
  }

  function buildDom(){
    const poolA=document.getElementById("poolA");
    const poolB=document.getElementById("poolB");
    const body=document.getElementById("bottleBody");

    poolA.innerHTML="";
    poolB.innerHTML="";
    body.querySelectorAll(".placed-mol").forEach(e=>e.remove());

    for(const group of ["a","b"]){
      for(let i=0;i<N;i++){
        (group==="a" ? poolA : poolB).appendChild(makeSource(group,i));
        body.appendChild(makePlaced(group,i));
      }
    }

    renderAll();
    renderFeedbackFromState();
    setTimeout(setHeight,40);
  }

  function renderOne(group,index){
    const src=sourceEl(group,index);
    const dst=placedEl(group,index);
    const pos=state[group][index];

    if(pos){
      src.style.visibility="hidden";
      dst.style.display="block";
      dst.style.left=Number(pos.x)+"px";
      dst.style.top=Number(pos.y)+"px";
    }else{
      src.style.visibility="visible";
      dst.style.display="none";
    }
  }

  function renderAll(){
    for(const g of ["a","b"]){
      for(let i=0;i<N;i++) renderOne(g,i);
    }
  }

  function renderFeedbackFromState(){
    if(state.success.a){
      setFeedback("a","good","✅ Zone a : modèle validé.");
    }else{
      setFeedback("a","neutral","Zone a : modèle non vérifié.");
    }
    if(state.success.b){
      setFeedback("b","good","✅ Zone b : modèle validé.");
    }else{
      setFeedback("b","neutral","Zone b : modèle non vérifié.");
    }
  }

  function startDrag(e){
    e.preventDefault();

    const el=e.currentTarget;
    const group=el.dataset.group;
    const index=Number(el.dataset.index);
    const rect=el.getBoundingClientRect();

    const ghost=el.cloneNode(true);
    ghost.removeAttribute("id");
    ghost.className="mol ghost";
    ghost.style.left=rect.left+"px";
    ghost.style.top=rect.top+"px";
    ghost.style.width=rect.width+"px";
    ghost.style.height=rect.height+"px";
    document.body.appendChild(ghost);

    drag={
      group,
      index,
      ghost,
      pointerId:e.pointerId,
      offsetX:e.clientX-rect.left,
      offsetY:e.clientY-rect.top,
      oldPosition:state[group][index] ? {...state[group][index]} : null
    };

    document.addEventListener("pointermove",moveDrag,{passive:false});
    document.addEventListener("pointerup",endDrag,{passive:false});
    document.addEventListener("pointercancel",cancelDrag,{passive:false});
  }

  function moveDrag(e){
    if(!drag || e.pointerId!==drag.pointerId) return;
    e.preventDefault();

    drag.ghost.style.left=(e.clientX-drag.offsetX)+"px";
    drag.ghost.style.top=(e.clientY-drag.offsetY)+"px";
    drag.ghost.style.transform="scale(1.08)";

    const body=document.getElementById("bottleBody");
    const br=body.getBoundingClientRect();
    const inside=
      e.clientX>=br.left && e.clientX<=br.right &&
      e.clientY>=br.top && e.clientY<=br.bottom;

    document.getElementById("zoneA").classList.toggle(
      "active", inside && drag.group==="a"
    );
    document.getElementById("zoneB").classList.toggle(
      "active", inside && drag.group==="b"
    );
  }

  function cleanupDrag(){
    document.getElementById("zoneA").classList.remove("active");
    document.getElementById("zoneB").classList.remove("active");

    if(drag?.ghost?.parentNode) drag.ghost.remove();

    document.removeEventListener("pointermove",moveDrag);
    document.removeEventListener("pointerup",endDrag);
    document.removeEventListener("pointercancel",cancelDrag);
  }

  function cancelDrag(){
    cleanupDrag();
    drag=null;
  }

  function endDrag(e){
    if(!drag || e.pointerId!==drag.pointerId) return;
    e.preventDefault();

    const body=document.getElementById("bottleBody");
    const br=body.getBoundingClientRect();

    const inside=
      e.clientX>=br.left && e.clientX<=br.right &&
      e.clientY>=br.top && e.clientY<=br.bottom;

    if(inside){
      const w=32,h=32;

      // Use the exact final position of the visible ghost.
      // This preserves the point where the pupil grabbed the molecule,
      // so the real molecule appears exactly where the ghost was released.
      const ghostRect=drag.ghost.getBoundingClientRect();
      let x=ghostRect.left-br.left;
      let y=ghostRect.top-br.top;

      // Keep the molecule fully inside the bottle, with only a tiny margin.
      x=Math.max(3,Math.min(body.clientWidth-w-3,x));

      // A molecule is accepted only in its intended compartment.
      // This avoids a large automatic jump across the divider.
      const centreY=y+(h/2);

      if(drag.group==="a"){
        if(centreY>=DIVIDER_Y){
          cleanupDrag();
          drag=null;
          return;
        }
        y=Math.max(3,Math.min(DIVIDER_Y-h-3,y));
      }else{
        if(centreY<=DIVIDER_Y+4){
          cleanupDrag();
          drag=null;
          return;
        }
        y=Math.max(
          DIVIDER_Y+7,
          Math.min(body.clientHeight-h-3,y)
        );
      }

      state[drag.group][drag.index]={
        x:Math.round(x*10)/10,
        y:Math.round(y*10)/10
      };
      state.success[drag.group]=false;
      renderOne(drag.group,drag.index);
      saveLocal();
    }

    cleanupDrag();
    drag=null;
  }

  function stats(points){
    if(points.length<2) return null;

    const nearest=[];
    for(let i=0;i<points.length;i++){
      let d=Infinity;
      for(let j=0;j<points.length;j++){
        if(i===j) continue;
        d=Math.min(
          d,
          Math.hypot(
            points[i].x-points[j].x,
            points[i].y-points[j].y
          )
        );
      }
      nearest.push(d);
    }

    const avgNearest=nearest.reduce((a,b)=>a+b,0)/nearest.length;

    // A molecule is considered "in contact or almost in contact"
    // when the centre-to-centre distance is <= 40 px.
    // Molecule diameter is 32 px, so this gives a small pedagogical tolerance.
    const closeFraction=
      nearest.filter(d=>d<=40).length / nearest.length;

    const xs=points.map(p=>p.x);
    const ys=points.map(p=>p.y);
    const width=Math.max(...xs)-Math.min(...xs);
    const height=Math.max(...ys)-Math.min(...ys);
    const meanY=ys.reduce((a,b)=>a+b,0)/ys.length;

    let alignedPairs=0,totalPairs=0;
    for(let i=0;i<points.length;i++){
      for(let j=i+1;j<points.length;j++){
        totalPairs++;
        if(
          Math.abs(points[i].x-points[j].x)<9 ||
          Math.abs(points[i].y-points[j].y)<9
        ){
          alignedPairs++;
        }
      }
    }

    return {
      avgNearest,
      closeFraction,
      width,
      height,
      meanY,
      alignment:totalPairs ? alignedPairs/totalPairs : 0
    };
  }

  function setFeedback(zone,kind,msg){
    const e=document.getElementById(zone==="a" ? "feedbackA" : "feedbackB");
    e.className="msg "+kind;
    e.textContent=msg;
  }

  function validate(){
    const a=state.a.filter(Boolean);
    const b=state.b.filter(Boolean);

    state.success.a=false;
    state.success.b=false;

    if(a.length<N){
      state.errors.a++;
      setFeedback(
        "a","hint",
        `Zone a : place encore ${N-a.length} molécule(s).`
      );
    }else{
      const s=stats(a);
      const ok=
        s.avgNearest>=58 &&
        s.width>=175 &&
        s.height>=175 &&
        s.alignment<0.38;

      state.success.a=ok;

      if(ok){
        setFeedback(
          "a","good",
          "✅ Zone a : ton modèle est cohérent."
        );
      }else{
        state.errors.a++;

        if(state.errors.a===1){
          setFeedback(
            "a","hint",
            "💡 Zone a : ce modèle ne correspond pas encore à l’état attendu. Observe la disposition de tes molécules et réessaie."
          );
        }else if(state.errors.a===2){
          setFeedback(
            "a","hint",
            "💡 Zone a : repense aux deux critères du cours : les molécules sont-elles proches ou espacées ? ordonnées ou désordonnées ?"
          );
        }else{
          setFeedback(
            "a","hint",
            "💡 Zone a : relis les propriétés de l’état que tu as identifié dans la partie précédente, puis modifie ton modèle."
          );
        }
      }
    }

    if(b.length<N){
      state.errors.b++;
      setFeedback(
        "b","hint",
        `Zone b : place encore ${N-b.length} molécule(s).`
      );
    }else{
      const s=stats(b);
      const ok=
        s.avgNearest<=42 &&
        s.closeFraction>=0.78 &&
        s.height<=118 &&
        s.meanY>=350 &&
        s.alignment<0.50;

      state.success.b=ok;

      if(ok){
        setFeedback(
          "b","good",
          "✅ Zone b : ton modèle est cohérent."
        );
      }else{
        state.errors.b++;

        if(state.errors.b===1){
          setFeedback(
            "b","hint",
            "💡 Zone b : ce modèle ne correspond pas encore à l’état attendu. Observe la disposition de tes molécules et réessaie."
          );
        }else if(state.errors.b===2){
          setFeedback(
            "b","hint",
            "💡 Zone b : repense aux deux critères du cours : les molécules sont-elles proches ou espacées ? ordonnées ou désordonnées ?"
          );
        }else{
          setFeedback(
            "b","hint",
            "💡 Zone b : relis les propriétés de l’état que tu as identifié dans la partie précédente, puis modifie ton modèle."
          );
        }
      }
    }

    saveLocal();
    sendValue();
    setTimeout(setHeight,40);
  }

  function resetZone(group){
    state[group]=Array(N).fill(null);
    state.success[group]=false;

    for(let i=0;i<N;i++){
      renderOne(group,i);
    }

    setFeedback(
      group,
      "neutral",
      `Zone ${group} : modèle remis à zéro.`
    );

    saveLocal();
    sendValue();
  }

  function resetAll(){
    // On remet les positions à zéro mais on conserve le nombre
    // d'erreurs de cette tentative.
    state.a=Array(N).fill(null);
    state.b=Array(N).fill(null);
    state.success.a=false;
    state.success.b=false;

    renderAll();
    setFeedback("a","neutral","Zone a : modèle remis à zéro.");
    setFeedback("b","neutral","Zone b : modèle remis à zéro.");

    saveLocal();
    sendValue();
  }

  function init(newGeneration,newStorageId){
    const changed=
      !initialized ||
      generation!==newGeneration ||
      storageId!==newStorageId;

    generation=newGeneration;
    storageId=newStorageId || "default";

    if(changed){
      state=loadLocal();
      buildDom();
      initialized=true;
    }else{
      setHeight();
    }
  }

  document.getElementById("resetA").addEventListener("click",()=>resetZone("a"));
  document.getElementById("resetB").addEventListener("click",()=>resetZone("b"));
  document.getElementById("resetAll").addEventListener("click",resetAll);
  document.getElementById("check").addEventListener("click",validate);

  window.addEventListener("message",(event)=>{
    const data=event.data || {};
    if(data.type==="streamlit:render"){
      const args=data.args || {};
      init(
        Number(args.generation || 0),
        String(args.storage_id || "default")
      );
    }
  });

  sendReady();

  // Permet aussi de tester le module HTML seul hors Streamlit.
  setTimeout(()=>{
    if(!initialized) init(0,"standalone");
  },250);
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex4_dragdrop_component_v31():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex4_dragdrop_component_v31"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(EX4_DRAGDROP_HTML, encoding="utf-8")
    return components.declare_component(
        "ex4_dragdrop_model_v31",
        path=str(component_dir),
    )


def render_ex4_dragdrop_model(generation):
    component = _ex4_dragdrop_component_v31()

    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )

    return component(
        generation=int(generation),
        storage_id=storage_id,
        key=f"ex4_dragdrop_v31_{generation}",
        default={
            "zone_a": False,
            "zone_b": False,
            "errors_a": 0,
            "errors_b": 0,
            "positions": {"a": [], "b": []},
        },
    )

# ============================================================
# EXERCICE 4 — PROPRIÉTÉS ET BOUTEILLE DE DIOXYGÈNE
# ============================================================

EXERCISE4_OXYGEN_IMAGE = "assets/chapitre_1/exercice 4/bouteille d oxygene.png"

EXERCISE4_PROPERTIES = [
    {
        "label": "Les molécules se touchent.",
        "answers": {"Solide", "Liquide"},
        "hint": "Dans quels états les molécules restent-elles très proches les unes des autres ?",
        "explanation": "Dans un solide et dans un liquide, les molécules sont compactes : elles sont très proches.",
    },
    {
        "label": "Les molécules sont espacées.",
        "answers": {"Gazeux"},
        "hint": "Cherche l’état dans lequel les molécules occupent tout le volume disponible.",
        "explanation": "Dans un gaz, les molécules sont dispersées et donc beaucoup plus espacées.",
    },
    {
        "label": "Les molécules sont disposées de façon ordonnée.",
        "answers": {"Solide"},
        "hint": "Dans quel état les molécules restent-elles rangées régulièrement ?",
        "explanation": "Dans un solide, les molécules sont compactes et ordonnées.",
    },
    {
        "label": "Les molécules sont disposées de façon désordonnée.",
        "answers": {"Liquide", "Gazeux"},
        "hint": "Deux états ont des molécules qui ne sont pas rangées régulièrement.",
        "explanation": "Dans un liquide et dans un gaz, les molécules sont désordonnées.",
    },
    {
        "label": "Les molécules sont libres de se déplacer.",
        "answers": {"Liquide", "Gazeux"},
        "hint": "Dans quels états les molécules peuvent-elles changer de position les unes par rapport aux autres ?",
        "explanation": "Dans un liquide et dans un gaz, les molécules sont mobiles.",
    },
]


def _ex4_prop_state(index, state_name):
    return st.session_state.get(f"ex4_prop_{index}_{state_name}", "idle")


def _ex4_handle_prop_click(index, state_name, answers):
    key = f"ex4_prop_{index}_{state_name}"
    current = st.session_state.get(key, "idle")
    st.session_state[key] = "selected" if current != "selected" else "idle"

    st.session_state.pop(f"ex4_prop_feedback_{index}", None)
    st.session_state.pop(f"ex4_prop_complete_{index}", None)


def _ex4_validate_prop_row(index, answers):
    mapping = {"solid": "Solide", "liquid": "Liquide", "gas": "Gazeux"}

    selected = {
        human
        for state_name, human in mapping.items()
        if st.session_state.get(f"ex4_prop_{index}_{state_name}") == "selected"
    }

    if not selected:
        st.session_state[f"ex4_prop_feedback_{index}"] = "empty"
        return

    if selected == set(answers):
        st.session_state[f"ex4_prop_complete_{index}"] = True
        st.session_state[f"ex4_prop_feedback_{index}"] = "correct"
    else:
        st.session_state[f"ex4_prop_complete_{index}"] = False
        err_key = f"ex4_prop_errors_{index}"
        st.session_state[err_key] = int(st.session_state.get(err_key, 0)) + 1
        st.session_state[f"ex4_prop_feedback_{index}"] = "wrong"


def _ex4_render_prop_button(index, state_name, answers):
    state = _ex4_prop_state(index, state_name)
    human = {"solid": "Solide", "liquid": "Liquide", "gas": "Gazeux"}[state_name]
    selected = state == "selected"

    st.button(
        f"✓ {human}" if selected else human,
        key=f"ex4_prop_btn_{index}_{state_name}",
        use_container_width=True,
        type="primary" if selected else "secondary",
        on_click=_ex4_handle_prop_click,
        args=(index, state_name, answers),
    )
    st.markdown(
        f'<div class="{"ex4-choice-selected" if selected else "ex4-choice-idle"}"></div>',
        unsafe_allow_html=True,
    )


def _normalize_oxygen_zone(value):
    value = str(value or "").strip().lower()
    value = (
        value.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ë", "e")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ä", "a")
        .replace("î", "i")
        .replace("ï", "i")
        .replace("ô", "o")
        .replace("ö", "o")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("ü", "u")
        .replace("ç", "c")
        .replace("’", "'")
    )
    value = " ".join(value.split())

    aliases = {
        "dioxygene gazeux": "gaz",
        "dioxygene gaz": "gaz",
        "gaz": "gaz",
        "gazeux": "gaz",
        "etat gazeux": "gaz",
        "etat gaz": "gaz",
        "dioxygene liquide": "liquide",
        "liquide": "liquide",
        "etat liquide": "liquide",
    }
    return aliases.get(value, value)


def _ex4_validate_zone(zone):
    generation = int(st.session_state.get("ex4_generation", 0))
    answer_key = f"ex4_zone_{generation}_{zone}"
    given = _normalize_oxygen_zone(st.session_state.get(answer_key, ""))
    expected = "gaz" if zone == "a" else "liquide"

    if not given:
        st.session_state[f"ex4_zone_empty_{zone}"] = True
        return

    st.session_state[f"ex4_zone_empty_{zone}"] = False

    if given == expected:
        st.session_state[f"ex4_zone_correct_{zone}"] = True
    else:
        st.session_state[f"ex4_zone_correct_{zone}"] = False
        key = f"ex4_zone_errors_{zone}"
        st.session_state[key] = int(st.session_state.get(key, 0)) + 1


def _ex4_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    touched = 0
    errors = 0

    if any(
        st.session_state.get(f"ex4_prop_{i}_{s}", "idle") != "idle"
        for i in range(len(EXERCISE4_PROPERTIES))
        for s in ("solid", "liquid", "gas")
    ):
        touched += 1

    generation = int(st.session_state.get("ex4_generation", 0))
    if any(
        str(st.session_state.get(f"ex4_zone_{generation}_{z}", "")).strip()
        for z in ("a", "b")
    ):
        touched += 1

    model_state = st.session_state.get("ex4_dragdrop_last_state")
    if isinstance(model_state, dict):
        pos = model_state.get("positions", {})
        if pos.get("a") or pos.get("b"):
            touched += 1

    errors += sum(
        int(st.session_state.get(f"ex4_prop_errors_{i}", 0))
        for i in range(len(EXERCISE4_PROPERTIES))
    )
    errors += sum(
        int(st.session_state.get(f"ex4_zone_errors_{z}", 0))
        for z in ("a", "b")
    )
    if isinstance(model_state, dict):
        errors += int(model_state.get("errors_a", 0) or 0)
        errors += int(model_state.get("errors_b", 0) or 0)

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == "exercise4_oxygen_bottle"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise4_oxygen_bottle",
        "resource_label": PILOT_CONTENTS["exercise4_oxygen_bottle"]["label"],
        "chapter": PILOT_CONTENTS["exercise4_oxygen_bottle"]["chapter"],
        "score_percent": None,
        "completed_items": touched,
        "total_items": 3,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise4_oxygen_bottle():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex4_"):
            st.session_state.pop(key, None)


def _ex4_start_new_attempt():
    _ex4_record_restart_if_needed()
    generation = int(st.session_state.get("ex4_generation", 0))
    reset_exercise4_oxygen_bottle()
    st.session_state["ex4_generation"] = generation + 1


def page_exercise4_oxygen_bottle():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise4_oxygen_bottle"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex4-box {
            background:#f5f9ff;
            border:1px solid #cfe0fb;
            border-radius:16px;
            padding:.9rem 1rem;
            margin:.5rem 0 1rem 0;
            color:#324a68;
        }
        .ex4-row-label {
            min-height:48px;
            display:flex;
            align-items:center;
            padding:0 .8rem;
            background:#f1f3f6;
            border:1px solid #dfe6ef;
            border-radius:12px;
            font-weight:800;
            color:#162b4d;
        }
        .ex4-feedback {
            min-height:48px;
            display:flex;
            align-items:center;
            padding:0 .7rem;
            border-radius:12px;
            font-size:.88rem;
            font-weight:700;
            background:#f8fafc;
            border:1px solid #e3e9f2;
        }
        .ex4-ok {background:#eefaf2;border-color:#cdebd6;color:#24623a;}
        .ex4-hint {background:#fff7e6;border-color:#f4d69b;color:#73541c;}
        .ex4-bad {background:#fff1f1;border-color:#f0c8c8;color:#7b2c2c;}

        div[data-testid="stButton"]:has(+ .ex4-choice-idle) button {
            background:#ffffff !important;
            border-color:#cfd8e6 !important;
            color:#18345d !important;
        }
        div[data-testid="stButton"]:has(+ .ex4-choice-selected) button {
            background:#3478e5 !important;
            border-color:#2764c2 !important;
            color:white !important;
        }

        .ex4-grid-title {
            font-weight:800;
            color:#16335f;
            margin:.25rem 0 .4rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Propriétés et bouteille de dioxygène</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🫧 Exercice 4 — Propriétés et bouteille de dioxygène</div>',
        unsafe_allow_html=True,
    )

    # ---------------- PARTIE 1 ----------------
    st.markdown("### 1. Propriétés des molécules")
    st.markdown(
        '<div class="ex4-box">Pour chaque proposition, clique sur le ou les états correspondants. '
        'La correction est immédiate.</div>',
        unsafe_allow_html=True,
    )

    for i, item in enumerate(EXERCISE4_PROPERTIES):
        c1, c2, c3, c4, c5, c6 = st.columns([2.7, .9, .9, .9, .9, 2.4], gap="small")
        with c1:
            st.markdown(f'<div class="ex4-row-label">{item["label"]}</div>', unsafe_allow_html=True)
        with c2:
            _ex4_render_prop_button(i, "solid", item["answers"])
        with c3:
            _ex4_render_prop_button(i, "liquid", item["answers"])
        with c4:
            _ex4_render_prop_button(i, "gas", item["answers"])
        with c5:
            st.button(
                "Valider",
                key=f"ex4_validate_prop_{i}",
                use_container_width=True,
                on_click=_ex4_validate_prop_row,
                args=(i, item["answers"]),
            )

        errors = int(st.session_state.get(f"ex4_prop_errors_{i}", 0))
        complete = bool(st.session_state.get(f"ex4_prop_complete_{i}", False))
        feedback_state = st.session_state.get(f"ex4_prop_feedback_{i}")

        with c6:
            if complete:
                fb = '<div class="ex4-feedback ex4-ok">✅ Bonne réponse.</div>'
            elif feedback_state == "empty":
                fb = '<div class="ex4-feedback ex4-hint">Choisis au moins une réponse.</div>'
            elif errors == 1:
                fb = f'<div class="ex4-feedback ex4-hint">💡 {item["hint"]}</div>'
            elif errors >= 2:
                ans = " + ".join(sorted(item["answers"]))
                fb = f'<div class="ex4-feedback ex4-bad">❌ {ans} — {item["explanation"]}</div>'
            else:
                fb = '<div class="ex4-feedback">Correction</div>'
            st.markdown(fb, unsafe_allow_html=True)

    # ---------------- PARTIE 2 ----------------
    st.markdown("### 2. Identifier les zones de la bouteille")
    st.markdown(
        '<div class="ex4-box">La bouteille contient uniquement du dioxygène. '
        'Lorsqu’on la déplace, on entend le bruit caractéristique d’un liquide. '
        'Identifie l’état du dioxygène dans les zones a et b.</div>',
        unsafe_allow_html=True,
    )

    img_path = Path(EXERCISE4_OXYGEN_IMAGE)
    if img_path.exists():
        st.image(str(img_path), width=700)
    else:
        st.warning(
            "Image manquante : ajoute « bouteille d oxygene.png » dans "
            "assets/chapitre_1/exercice 4/."
        )

    generation = int(st.session_state.get("ex4_generation", 0))
    z1, z2 = st.columns(2, gap="large")

    for col, zone in [(z1, "a"), (z2, "b")]:
        with col:
            st.text_input(
                f"Zone {zone} — Quel est l’état du dioxygène ?",
                key=f"ex4_zone_{generation}_{zone}",
                placeholder="Écris ta réponse puis appuie sur Entrée",
                on_change=_ex4_validate_zone,
                args=(zone,),
                disabled=bool(st.session_state.get(f"ex4_zone_correct_{zone}", False)),
            )
            st.button(
                "Vérifier",
                key=f"ex4_zone_btn_{zone}",
                use_container_width=True,
                on_click=_ex4_validate_zone,
                args=(zone,),
                disabled=bool(st.session_state.get(f"ex4_zone_correct_{zone}", False)),
            )

            errors = int(st.session_state.get(f"ex4_zone_errors_{zone}", 0))
            correct = bool(st.session_state.get(f"ex4_zone_correct_{zone}", False))

            if correct:
                expected = "gazeux" if zone == "a" else "liquide"
                st.success(f"✅ Zone {zone} : dioxygène {expected}.")
            elif errors == 1:
                if zone == "a":
                    st.info("💡 Observe la partie supérieure de la bouteille : quel état occupe tout l’espace disponible ?")
                else:
                    st.info("💡 Le document précise qu’on entend le bruit caractéristique lorsqu’on déplace la bouteille.")
            elif errors >= 2:
                expected = "gazeux" if zone == "a" else "liquide"
                st.error(f"❌ Zone {zone} : le dioxygène y est {expected}.")

    # ---------------- PARTIE 3 ----------------
    st.markdown("### 3. Construire un modèle moléculaire")
    st.markdown(
        '<div class="ex4-box">'
        'Fais glisser les molécules directement dans le schéma de la bouteille. '
        'Pour la zone <strong>a</strong>, représente le dioxygène gazeux ; '
        'pour la zone <strong>b</strong>, représente le dioxygène liquide. '
        'Tu peux déplacer les molécules autant de fois que nécessaire avant de vérifier.'
        '</div>',
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex4_generation", 0))
    model_state = render_ex4_dragdrop_model(generation)

    if isinstance(model_state, dict):
        st.session_state["ex4_dragdrop_last_state"] = model_state
        part3_ok = bool(model_state.get("zone_a")) and bool(model_state.get("zone_b"))
    else:
        part3_ok = False

    # ---------------- BILAN ----------------
    part1_ok = all(
        st.session_state.get(f"ex4_prop_complete_{i}", False)
        for i in range(len(EXERCISE4_PROPERTIES))
    )
    part2_ok = all(
        st.session_state.get(f"ex4_zone_correct_{z}", False)
        for z in ("a", "b")
    )
    completed_parts = sum([part1_ok, part2_ok, part3_ok])

    st.markdown("### Ton avancement")
    st.progress(completed_parts / 3)
    st.write(f"**{completed_parts} / 3 parties réussies**")

    c_reset, c_space = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex4_oxygen_bottle",
            use_container_width=True,
        ):
            _ex4_start_new_attempt()
            st.rerun()

    if completed_parts == 3:
        st.success("🎉 Bravo ! Tu as réussi l’ensemble de l’exercice.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex4_result_saved", False)
        ):
            model_errors = 0
            if isinstance(model_state, dict):
                model_errors = (
                    int(model_state.get("errors_a", 0) or 0)
                    + int(model_state.get("errors_b", 0) or 0)
                )

            total_errors = (
                sum(int(st.session_state.get(f"ex4_prop_errors_{i}", 0)) for i in range(len(EXERCISE4_PROPERTIES)))
                + sum(int(st.session_state.get(f"ex4_zone_errors_{z}", 0)) for z in ("a", "b"))
                + model_errors
            )
            record_training_result(
                student,
                "exercise4_oxygen_bottle",
                round(100 * 3 / max(3, 3 + total_errors)),
                3,
                3,
                errors=total_errors,
            )
            st.session_state["ex4_result_saved"] = True



# ============================================================
# EXERCICE 5 — MODÉLISER UN MÉLANGE : L’EAU DE MER
# ============================================================

EXERCISE5_SEAWATER_IMAGE = "assets/chapitre_1/exercice 5/schéma melange eau de mer.png"


def _ex5_normalize(value):
    value = str(value or "").strip().lower()
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "’": "'", "œ": "oe",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)

    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    return " ".join(value.split())


def _ex5_is_mixture(value):
    v = _ex5_normalize(value)
    return v in {"melange", "un melange", "c'est un melange", "c est un melange"}


def _ex5_is_pure(value):
    v = _ex5_normalize(value)
    return v in {
        "corps pur",
        "un corps pur",
        "c'est un corps pur",
        "c est un corps pur",
        "pur",
    }


def _ex5_q1_justification_ok(value):
    """Accepte différentes formulations simples montrant que plusieurs constituants sont présents."""
    v = _ex5_normalize(value)

    strong_phrases = [
        "eau et sel",
        "eau et du sel",
        "eau avec du sel",
        "eau avec le sel",
        "plusieurs substances",
        "plusieurs constituants",
        "plusieurs especes",
        "plusieurs sortes",
        "differentes substances",
        "differents constituants",
        "sels dissous",
        "sel dissous",
    ]
    if any(p in v for p in strong_phrases):
        return True

    # Accepte aussi les formulations naturelles du type :
    # "il y a de l'eau et du sel", "l'eau contient du sel", etc.
    has_water = "eau" in v
    has_salt = "sel" in v or "sels" in v
    return has_water and has_salt


def _ex5_q3_justification_ok(value):
    """Accepte plusieurs raisonnements corrects pour justifier le choix d’Inès.

    Deux types de justification sont admis :
    1) l’élève s’appuie directement sur le modèle microscopique
       (plusieurs sortes de particules) ;
    2) l’élève relie ses réponses précédentes :
       l’eau de mer est un mélange et le modèle d’Inès représente un mélange.
    """
    v = _ex5_normalize(value)

    # Raisonnement fondé directement sur l'observation des particules.
    particle_phrases = [
        "deux sortes",
        "plusieurs sortes",
        "deux types",
        "plusieurs types",
        "deux especes",
        "plusieurs especes",
        "particules differentes",
        "particules de couleurs differentes",
        "deux couleurs",
        "vertes et orange",
        "vert et orange",
    ]
    if any(p in v for p in particle_phrases):
        return True

    if "vert" in v and "orange" in v:
        return True

    # Raisonnement logique à partir des questions précédentes, par exemple :
    # « L’eau de mer est un mélange et Inès a représenté un mélange. »
    mentions_seawater = (
        "eau de mer" in v
        or ("eau" in v and "mer" in v)
    )
    mentions_mixture = "melange" in v
    links_to_model = any(
        term in v
        for term in [
            "ines",
            "modele",
            "represente",
            "representation",
            "elle",
            "son modele",
        ]
    )

    return mentions_seawater and mentions_mixture and links_to_model


def _ex5_clear_question_feedback(question):
    """Masque l'ancien retour dès que l'élève modifie sa réponse."""
    st.session_state.pop(f"ex5_q{question}_feedback", None)


def _ex5_validate_q1():
    generation = int(st.session_state.get("ex5_generation", 0))
    answer = st.session_state.get(f"ex5_q1_answer_{generation}", "")
    justification = st.session_state.get(f"ex5_q1_justification_{generation}", "")

    if not str(answer).strip() or not str(justification).strip():
        st.session_state["ex5_q1_feedback"] = "empty"
        return

    if _ex5_is_mixture(answer) and _ex5_q1_justification_ok(justification):
        st.session_state["ex5_q1_correct"] = True
        st.session_state["ex5_q1_feedback"] = "correct"
    else:
        st.session_state["ex5_q1_correct"] = False
        st.session_state["ex5_q1_errors"] = int(st.session_state.get("ex5_q1_errors", 0)) + 1
        st.session_state["ex5_q1_feedback"] = "wrong"


def _ex5_validate_q2():
    generation = int(st.session_state.get("ex5_generation", 0))
    lucas = st.session_state.get(f"ex5_q2_lucas_{generation}", "")
    ines = st.session_state.get(f"ex5_q2_ines_{generation}", "")

    if not str(lucas).strip() or not str(ines).strip():
        st.session_state["ex5_q2_feedback"] = "empty"
        return

    if _ex5_is_pure(lucas) and _ex5_is_mixture(ines):
        st.session_state["ex5_q2_correct"] = True
        st.session_state["ex5_q2_feedback"] = "correct"
    else:
        st.session_state["ex5_q2_correct"] = False
        st.session_state["ex5_q2_errors"] = int(st.session_state.get("ex5_q2_errors", 0)) + 1
        st.session_state["ex5_q2_feedback"] = "wrong"


def _ex5_validate_q3():
    generation = int(st.session_state.get("ex5_generation", 0))
    student_answer = _ex5_normalize(
        st.session_state.get(f"ex5_q3_student_{generation}", "")
    )
    justification = st.session_state.get(f"ex5_q3_justification_{generation}", "")

    if not student_answer or not str(justification).strip():
        st.session_state["ex5_q3_feedback"] = "empty"
        return

    if student_answer == "ines" and _ex5_q3_justification_ok(justification):
        st.session_state["ex5_q3_correct"] = True
        st.session_state["ex5_q3_feedback"] = "correct"
    else:
        st.session_state["ex5_q3_correct"] = False
        st.session_state["ex5_q3_errors"] = int(st.session_state.get("ex5_q3_errors", 0)) + 1
        st.session_state["ex5_q3_feedback"] = "wrong"


def _ex5_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex5_generation", 0))

    touched = 0
    if (
        str(st.session_state.get(f"ex5_q1_answer_{generation}", "")).strip()
        or str(st.session_state.get(f"ex5_q1_justification_{generation}", "")).strip()
    ):
        touched += 1

    if (
        str(st.session_state.get(f"ex5_q2_lucas_{generation}", "")).strip()
        or str(st.session_state.get(f"ex5_q2_ines_{generation}", "")).strip()
    ):
        touched += 1

    if (
        str(st.session_state.get(f"ex5_q3_student_{generation}", "")).strip()
        or str(st.session_state.get(f"ex5_q3_justification_{generation}", "")).strip()
    ):
        touched += 1

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    total_errors = sum(
        int(st.session_state.get(key, 0))
        for key in ("ex5_q1_errors", "ex5_q2_errors", "ex5_q3_errors")
    )

    rows = get_activity_log(teacher_id)
    previous = [
        row for row in rows
        if row.get("student_id") == student.get("id")
        and row.get("resource_id") == "exercise5_seawater_mixture"
        and row.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise5_seawater_mixture",
        "resource_label": PILOT_CONTENTS["exercise5_seawater_mixture"]["label"],
        "chapter": PILOT_CONTENTS["exercise5_seawater_mixture"]["chapter"],
        "score_percent": None,
        "completed_items": touched,
        "total_items": 3,
        "errors": total_errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise5_seawater_mixture():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex5_"):
            st.session_state.pop(key, None)


def _ex5_start_new_attempt():
    _ex5_record_restart_if_needed()
    generation = int(st.session_state.get("ex5_generation", 0))
    reset_exercise5_seawater_mixture()
    st.session_state["ex5_generation"] = generation + 1


def _ex5_feedback_box(question):
    feedback = st.session_state.get(f"ex5_q{question}_feedback")
    errors = int(st.session_state.get(f"ex5_q{question}_errors", 0))
    correct = bool(st.session_state.get(f"ex5_q{question}_correct", False))

    if correct:
        if question == 1:
            st.markdown(
                '<div class="ex5-feedback ex5-ok">✅ Bonne réponse. '
                'Ta réponse et ta justification sont cohérentes.</div>',
                unsafe_allow_html=True,
            )
        elif question == 2:
            st.markdown(
                '<div class="ex5-feedback ex5-ok">✅ Bonne réponse pour les deux modèles.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="ex5-feedback ex5-ok">✅ Bonne réponse. '
                'Tu as correctement identifié le modèle de l’eau de mer.</div>',
                unsafe_allow_html=True,
            )
        return

    if feedback == "empty":
        st.markdown(
            '<div class="ex5-feedback ex5-hint">✏️ Complète toutes les parties de ta réponse avant de valider.</div>',
            unsafe_allow_html=True,
        )
        return

    if feedback != "wrong":
        return

    if question == 1:
        if errors == 1:
            msg = (
                "💡 Réfléchis à ce que contient réellement l’eau de mer : "
                "est-elle constituée d’une seule substance ?"
            )
        elif errors == 2:
            msg = (
                "📘 Rappel : un corps pur ne contient qu’une seule espèce chimique ; "
                "un mélange en contient plusieurs."
            )
        else:
            msg = (
                "🔎 L’eau de mer contient de l’eau et des substances dissoutes, notamment des sels. "
                "Elle correspond donc à un mélange."
            )

    elif question == 2:
        if errors == 1:
            msg = (
                "💡 Observe uniquement le nombre de sortes de particules représentées "
                "dans chacun des deux béchers."
            )
        elif errors == 2:
            msg = (
                "📘 Rappel : une seule sorte de particules correspond à un corps pur ; "
                "plusieurs sortes correspondent à un mélange."
            )
        else:
            msg = (
                "🔎 Dans le modèle de Lucas, une seule sorte de particules est représentée : "
                "c’est un corps pur. Dans celui d’Inès, deux sortes sont représentées : "
                "c’est un mélange."
            )

    else:
        if errors == 1:
            msg = (
                "💡 Appuie-toi sur ce que tu as établi dans les deux questions précédentes "
                "ou sur ce que tu observes dans le modèle choisi."
            )
        elif errors == 2:
            msg = (
                "📘 Pour représenter un mélange, le modèle doit montrer plusieurs sortes de particules."
            )
        else:
            msg = (
                "🔎 C’est Inès qui a correctement représenté l’eau de mer : "
                "son modèle comporte plusieurs sortes de particules."
            )

    css_class = "ex5-hint" if errors < 3 else "ex5-correction"
    st.markdown(
        f'<div class="ex5-feedback {css_class}">{msg}</div>',
        unsafe_allow_html=True,
    )


def page_exercise5_seawater_mixture():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise5_seawater_mixture"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex5-box {
            background:#f5f9ff;
            border:1px solid #cfe0fb;
            border-radius:16px;
            padding:.9rem 1rem;
            margin:.55rem 0 1rem 0;
            color:#324a68;
        }
        .ex5-names {
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:2rem;
            margin:.35rem 7% .25rem 7%;
        }
        .ex5-name {
            text-align:center;
            font-weight:900;
            font-size:1.25rem;
            color:#ffffff;
            padding:.48rem .7rem;
            border-radius:999px;
        }
        .ex5-lucas {background:#139ed0;}
        .ex5-ines {background:#8242b3;}
        .ex5-feedback {
            border-radius:12px;
            padding:.82rem 1rem;
            margin:.5rem 0 .9rem 0;
            font-weight:700;
            line-height:1.45;
            font-size:1rem;
        }
        .ex5-ok {
            background:#eefaf2;
            border:1px solid #cdebd6;
            color:#24623a;
        }
        .ex5-hint {
            background:#fff7e6;
            border:1px solid #f4d69b;
            color:#73541c;
        }
        .ex5-correction {
            background:#fff1f1;
            border:1px solid #f0c8c8;
            color:#7b2c2c;
        }
        .ex5-question {
            background:#f8fafc;
            border:1px solid #e1e7f0;
            border-radius:15px;
            padding:.9rem 1rem .4rem 1rem;
            margin:1rem 0;
        }

        /* Champs de réponse plus lisibles pour les élèves */
        div[data-testid="stTextInput"] input {
            font-size:1.15rem !important;
            line-height:1.5 !important;
            min-height:3.15rem !important;
            padding:.72rem .9rem !important;
        }

        div[data-testid="stTextArea"] textarea {
            font-size:1.15rem !important;
            line-height:1.55 !important;
            padding:.8rem .9rem !important;
        }

        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label {
            font-size:1rem !important;
            font-weight:700 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Modéliser un mélange : l’eau de mer</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🌊 Exercice 5 — Modéliser un mélange : l’eau de mer</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ex5-box"><strong>Objectif :</strong> différencier un corps pur '
        'et un mélange à l’échelle microscopique.<br><br>'
        'Lucas et Inès cherchent à modéliser l’eau de mer. '
        'Observe attentivement leurs deux propositions.</div>',
        unsafe_allow_html=True,
    )

    image_path = Path(EXERCISE5_SEAWATER_IMAGE)

    # Schéma volontairement limité en largeur : il doit être lisible sans
    # occuper tout l'écran. Les prénoms restent alignés avec les deux béchers.
    image_left, image_center, image_right = st.columns([1.2, 4.6, 1.2])

    with image_center:
        st.markdown(
            """
            <div class="ex5-names">
                <div class="ex5-name ex5-lucas">Lucas</div>
                <div class="ex5-name ex5-ines">Inès</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if image_path.exists():
            st.image(str(image_path), use_container_width=True)
        else:
            st.warning(
                "Image manquante : ajoute « schéma melange eau de mer.png » dans "
                "assets/chapitre_1/exercice 5/."
            )

    generation = int(st.session_state.get("ex5_generation", 0))

    # ---------------- QUESTION 1 ----------------
    st.markdown('<div class="ex5-question">', unsafe_allow_html=True)
    st.markdown("### 1. L’eau de mer est-elle un mélange ou un corps pur ? Justifie.")

    st.text_input(
        "Ta réponse",
        key=f"ex5_q1_answer_{generation}",
        placeholder="Écris : corps pur ou mélange",
        disabled=bool(st.session_state.get("ex5_q1_correct", False)),
        on_change=_ex5_clear_question_feedback,
        args=(1,),
    )
    st.text_area(
        "Ta justification",
        key=f"ex5_q1_justification_{generation}",
        placeholder="Explique en une phrase pourquoi.",
        height=90,
        disabled=bool(st.session_state.get("ex5_q1_correct", False)),
        on_change=_ex5_clear_question_feedback,
        args=(1,),
    )
    st.button(
        "Valider la question 1",
        key="ex5_validate_q1",
        use_container_width=True,
        on_click=_ex5_validate_q1,
        disabled=bool(st.session_state.get("ex5_q1_correct", False)),
    )
    _ex5_feedback_box(1)
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- QUESTION 2 ----------------
    st.markdown('<div class="ex5-question">', unsafe_allow_html=True)
    st.markdown(
        "### 2. Le modèle proposé par Lucas représente-t-il un corps pur ou un mélange ? "
        "Et celui d’Inès ?"
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.text_input(
            "Modèle de Lucas",
            key=f"ex5_q2_lucas_{generation}",
            placeholder="Corps pur ou mélange ?",
            disabled=bool(st.session_state.get("ex5_q2_correct", False)),
            on_change=_ex5_clear_question_feedback,
            args=(2,),
        )
    with c2:
        st.text_input(
            "Modèle d’Inès",
            key=f"ex5_q2_ines_{generation}",
            placeholder="Corps pur ou mélange ?",
            disabled=bool(st.session_state.get("ex5_q2_correct", False)),
            on_change=_ex5_clear_question_feedback,
            args=(2,),
        )

    st.button(
        "Valider la question 2",
        key="ex5_validate_q2",
        use_container_width=True,
        on_click=_ex5_validate_q2,
        disabled=bool(st.session_state.get("ex5_q2_correct", False)),
    )
    _ex5_feedback_box(2)
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- QUESTION 3 ----------------
    st.markdown('<div class="ex5-question">', unsafe_allow_html=True)
    st.markdown(
        "### 3. Lequel des deux élèves a correctement représenté l’eau de mer ? Explique pourquoi."
    )

    st.text_input(
        "Nom de l’élève",
        key=f"ex5_q3_student_{generation}",
        placeholder="Lucas ou Inès",
        disabled=bool(st.session_state.get("ex5_q3_correct", False)),
        on_change=_ex5_clear_question_feedback,
        args=(3,),
    )
    st.text_area(
        "Ton explication",
        key=f"ex5_q3_justification_{generation}",
        placeholder="Explique ce que tu observes dans son modèle.",
        height=90,
        disabled=bool(st.session_state.get("ex5_q3_correct", False)),
        on_change=_ex5_clear_question_feedback,
        args=(3,),
    )

    st.button(
        "Valider la question 3",
        key="ex5_validate_q3",
        use_container_width=True,
        on_click=_ex5_validate_q3,
        disabled=bool(st.session_state.get("ex5_q3_correct", False)),
    )
    _ex5_feedback_box(3)
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- BILAN ----------------
    completed = sum(
        bool(st.session_state.get(f"ex5_q{i}_correct", False))
        for i in (1, 2, 3)
    )

    st.markdown("### Ton avancement")
    st.progress(completed / 3)
    st.write(f"**{completed} / 3 questions réussies**")

    c_reset, _ = st.columns([1.4, 4.6])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex5_seawater_mixture",
            use_container_width=True,
        ):
            _ex5_start_new_attempt()
            st.rerun()

    if completed == 3:
        st.success("🎉 Bravo ! Tu sais distinguer un corps pur d’un mélange à partir d’un modèle microscopique.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex5_result_saved", False)
        ):
            total_errors = sum(
                int(st.session_state.get(key, 0))
                for key in ("ex5_q1_errors", "ex5_q2_errors", "ex5_q3_errors")
            )

            score = round(100 * 3 / max(3, 3 + total_errors))

            record_training_result(
                student,
                "exercise5_seawater_mixture",
                score,
                3,
                3,
                errors=total_errors,
            )
            st.session_state["ex5_result_saved"] = True



# ============================================================
# EXERCICE 6 — LE MYSTÈRE DU VOLUME PERDU : EAU + ALCOOL
# ============================================================

def _ex6_normalize(value):
    value = str(value or "").strip().lower()
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "’": "'", "œ": "oe",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    return " ".join(value.split())


def _ex6_clear_feedback(question):
    st.session_state.pop(f"ex6_q{question}_feedback", None)


def _ex6_q1_ok(value):
    """Analogie billes/sable : les grains fins occupent les espaces entre les grosses billes."""
    v = _ex6_normalize(value)
    idea_gap = any(x in v for x in [
        "espace", "espaces", "interstice", "interstices", "trou", "trous",
        "vide", "vides", "entre les billes", "entre elles",
    ])
    idea_fill = any(x in v for x in [
        "sable", "grain", "grains", "petit", "petits", "fine", "fin",
        "remplit", "remplissent", "occupe", "occupent", "se glisse", "se glissent",
    ])
    idea_not_sum = any(x in v for x in [
        "moins", "inferieur", "pas egal", "n est pas egal", "ne sera pas egal",
        "diminue", "plus petit",
    ])
    return (idea_gap and idea_fill) or (idea_not_sum and idea_fill)


def _ex6_q2_ok(value):
    """Les molécules d'eau, plus petites, occupent des espaces entre celles d'alcool."""
    v = _ex6_normalize(value)
    water = "eau" in v
    smaller = any(x in v for x in ["plus petite", "plus petites", "petite", "petites"])
    alcohol = "alcool" in v
    gap = any(x in v for x in [
        "espace", "espaces", "interstice", "interstices", "entre",
        "se glisse", "se glissent", "occupe", "occupent",
    ])
    compact = any(x in v for x in [
        "moins de place", "moins de volume", "volume diminue",
        "volume baisse", "plus compact", "rapproche",
    ])
    return water and alcohol and smaller and gap and (compact or "volume" in v)


def _ex6_q3_ok(value):
    """Conservation de la masse : aucune molécule ne disparaît, même quantité de matière."""
    v = _ex6_normalize(value)
    same_matter = any(x in v for x in [
        "meme nombre", "autant de molecule", "autant de molecules",
        "aucune molecule ne disparait", "aucune molecule disparait",
        "rien ne disparait", "rien n est perdu", "matiere se conserve",
        "masse se conserve", "meme quantite", "quantite de matiere",
        "molecules sont toujours presentes", "molecules restent presentes",
    ])
    no_loss = any(x in v for x in [
        "ne disparait", "ne disparaissent", "pas perdu", "pas de perte",
        "conserve", "conservation",
    ])
    return same_matter or (("molecule" in v or "matiere" in v) and no_loss)


def _ex6_validate_q1():
    generation = int(st.session_state.get("ex6_generation", 0))
    value = st.session_state.get(f"ex6_q1_{generation}", "")
    if not str(value).strip():
        st.session_state["ex6_q1_feedback"] = "empty"
        return
    if _ex6_q1_ok(value):
        st.session_state["ex6_q1_correct"] = True
        st.session_state["ex6_q1_feedback"] = "correct"
    else:
        st.session_state["ex6_q1_correct"] = False
        st.session_state["ex6_q1_errors"] = int(st.session_state.get("ex6_q1_errors", 0)) + 1
        st.session_state["ex6_q1_feedback"] = "wrong"


def _ex6_validate_q2():
    generation = int(st.session_state.get("ex6_generation", 0))
    value = st.session_state.get(f"ex6_q2_{generation}", "")
    if not str(value).strip():
        st.session_state["ex6_q2_feedback"] = "empty"
        return
    if _ex6_q2_ok(value):
        st.session_state["ex6_q2_correct"] = True
        st.session_state["ex6_q2_feedback"] = "correct"
    else:
        st.session_state["ex6_q2_correct"] = False
        st.session_state["ex6_q2_errors"] = int(st.session_state.get("ex6_q2_errors", 0)) + 1
        st.session_state["ex6_q2_feedback"] = "wrong"


def _ex6_validate_q3():
    generation = int(st.session_state.get("ex6_generation", 0))
    value = st.session_state.get(f"ex6_q3_{generation}", "")
    if not str(value).strip():
        st.session_state["ex6_q3_feedback"] = "empty"
        return
    if _ex6_q3_ok(value):
        st.session_state["ex6_q3_correct"] = True
        st.session_state["ex6_q3_feedback"] = "correct"
    else:
        st.session_state["ex6_q3_correct"] = False
        st.session_state["ex6_q3_errors"] = int(st.session_state.get("ex6_q3_errors", 0)) + 1
        st.session_state["ex6_q3_feedback"] = "wrong"


def _ex6_feedback(question):
    feedback = st.session_state.get(f"ex6_q{question}_feedback")
    errors = int(st.session_state.get(f"ex6_q{question}_errors", 0))
    correct = bool(st.session_state.get(f"ex6_q{question}_correct", False))

    if correct:
        messages = {
            1: "✅ Bonne réponse ! Tu as bien utilisé l’analogie entre les grosses billes et le sable fin.",
            2: "✅ Bonne réponse ! Ton explication relie correctement la taille des molécules et le fait que le volume final soit inférieur à la somme des volumes initiaux.",
            3: "✅ Bonne réponse ! Le volume peut changer sans disparition de matière : la masse se conserve.",
        }
        st.markdown(
            f'<div class="ex6-feedback ex6-ok">{messages[question]}</div>',
            unsafe_allow_html=True,
        )
        return

    if feedback == "empty":
        st.markdown(
            '<div class="ex6-feedback ex6-hint">✏️ Écris une réponse avant de valider.</div>',
            unsafe_allow_html=True,
        )
        return

    if feedback != "wrong":
        return

    if question == 1:
        if errors == 1:
            msg = "💡 Imagine ce qu’il reste entre de grosses billes placées les unes contre les autres."
        elif errors == 2:
            msg = "📘 Le sable est constitué de grains beaucoup plus petits que les grosses billes. Que peuvent faire ces petits grains ?"
        else:
            msg = "🔎 Les grains de sable peuvent occuper une partie des espaces laissés entre les grosses billes : le volume final peut donc être inférieur à la somme des deux volumes de départ."

    elif question == 2:
        if errors == 1:
            msg = "💡 Reprends l’analogie précédente et compare maintenant la taille des molécules d’eau et d’alcool."
        elif errors == 2:
            msg = "📘 Dans le modèle simplifié utilisé ici, les molécules d’eau sont représentées plus petites. Réfléchis à la façon dont les deux sortes de molécules peuvent se réorganiser lors du mélange."
        else:
            msg = "🔎 Lors du mélange, les molécules d’eau et d’alcool se réorganisent de façon plus compacte. Dans notre modèle simplifié, cela peut être rapproché de l’analogie des petites particules qui occupent des espaces entre de plus grosses."

    else:
        if errors == 1:
            msg = "💡 Demande-toi si des molécules ont disparu pendant le mélange."
        elif errors == 2:
            msg = "📘 Compare le nombre de molécules avant et après : la disposition peut changer sans que la matière disparaisse."
        else:
            msg = "🔎 Aucune molécule n’est perdue : on retrouve la même quantité de matière avant et après le mélange. La masse totale reste donc la même."

    css = "ex6-hint" if errors < 3 else "ex6-correction"
    st.markdown(
        f'<div class="ex6-feedback {css}">{msg}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# MODULE INTERACTIF EXERCICE 6 — MODÉLISATION EAU + ALCOOL
# ============================================================

EX6_MIXTURE_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  color:#17345f;
  background:#fff;
}
.wrap{max-width:1120px;margin:auto;padding:8px 10px 14px}
.intro{
  background:#f5f9ff;
  border:1px solid #cfe0fb;
  border-radius:14px;
  padding:12px 15px;
  margin-bottom:10px;
  line-height:1.5;
  font-size:14px;
}
.model-note{
  background:#fff8e8;
  border:1px solid #efd89c;
  color:#6f541d;
  border-radius:12px;
  padding:10px 13px;
  margin:0 0 14px;
  line-height:1.45;
  font-size:13px;
}
.legend{
  display:flex;
  justify-content:center;
  gap:28px;
  flex-wrap:wrap;
  margin:8px 0 16px;
  font-size:13px
}
.legend span{display:flex;align-items:center;gap:8px}
.dot{
  display:inline-block;
  border-radius:50%;
  border:3px solid
}
.dot.water{
  width:20px;height:20px;
  background:#36bdf1;border-color:#147ba6
}
.dot.alcohol{
  width:48px;height:48px;
  background:#ff9a32;border-color:#c86a13
}

.activity-title{
  text-align:center;
  font-weight:900;
  font-size:17px;
  color:#16335f;
  margin:4px 0 12px;
}

.final-area{
  display:grid;
  grid-template-columns:250px 1fr 250px;
  gap:18px;
  align-items:start
}
.tray{
  background:#f7f9fc;
  border:1px solid #cfdbea;
  border-radius:16px;
  padding:13px;
  min-height:245px;
  text-align:center
}
.tray h4{
  margin:0 0 5px;
  font-size:16px;
  color:#17345f
}
.tray p{
  margin:0 0 11px;
  color:#6e7c90;
  font-size:12px;
  line-height:1.4
}
.pool{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  justify-content:center;
  align-content:flex-start;
  min-height:145px;
  padding-top:5px
}

.particle{
  position:absolute;
  border-radius:50%;
  box-shadow:0 2px 5px #0002
}
.particle.water{
  width:22px;height:22px;
  background:radial-gradient(circle at 32% 28%,#a9ecff 0 18%,#36bdf1 20% 100%);
  border:3px solid #147ba6
}
.particle.alcohol{
  width:60px;height:60px;
  background:radial-gradient(circle at 32% 28%,#ffd09b 0 18%,#ff9a32 20% 100%);
  border:3px solid #c86a13
}
.source{
  position:relative;
  flex:0 0 auto;
  cursor:grab;
  touch-action:none;
  user-select:none;
  -webkit-user-select:none
}
.placed{
  display:none;
  z-index:30;
  cursor:grab;
  touch-action:none;
  user-select:none;
  -webkit-user-select:none
}
.ghost{
  position:fixed!important;
  z-index:99999!important;
  pointer-events:none!important;
  transform:scale(1.05)
}

.center{min-width:0}
.final-label{
  text-align:center;
  font-weight:900;
  font-size:16px;
  margin:0 0 8px;
  color:#17345f
}
.final-subtitle{
  text-align:center;
  font-size:12px;
  color:#6e7c90;
  margin:-3px 0 8px
}
.final-beaker-wrap{max-width:255px;margin:auto}
.final-beaker{
  position:relative;
  height:310px;
  border:5px solid #25313b;
  border-top:0;
  border-radius:0 0 46px 46px;
  overflow:hidden;
  background:linear-gradient(90deg,#f3fffd,#fff,#f0fbff)
}
.bottom-zone{
  position:absolute;
  left:0;right:0;bottom:0;height:72%;
  background:linear-gradient(to top,rgba(96,211,221,.08),rgba(255,255,255,0));
  pointer-events:none
}

.controls{
  display:flex;
  justify-content:center;
  gap:9px;
  flex-wrap:wrap;
  margin:13px 0 8px
}
button{
  border:1px solid #bfcde0;
  border-radius:11px;
  padding:9px 14px;
  font-weight:750;
  background:#fff;
  color:#17345f;
  cursor:pointer
}
button.primary{
  background:#1f6fd6;
  border-color:#1b61b9;
  color:#fff
}
.feedback{
  border-radius:12px;
  padding:11px 13px;
  font-weight:700;
  margin-top:8px;
  line-height:1.45
}
.neutral{
  background:#f7f9fc;
  border:1px solid #dfe6ef;
  color:#6e7c90
}
.good{
  background:#eaf8ef;
  border:1px solid #b8e2c4;
  color:#24623a
}
.hint{
  background:#fff8e8;
  border:1px solid #efd89c;
  color:#73541c
}

@media(max-width:900px){
  .final-area{grid-template-columns:1fr}
  .tray{min-height:0}
  .pool{min-height:80px}
}
</style>
</head>

<body>
<div class="wrap">

  <div class="intro">
    <strong>4. Modélise l’état initial et l’état final.</strong><br>
    À gauche et à droite, les deux sortes de molécules sont séparées :
    c’est l’<strong>état initial</strong>. Fais-les glisser dans le récipient central
    pour construire un modèle de l’<strong>état final après le mélange</strong>.
  </div>

  <div class="model-note">
    <strong>Attention : c’est un modèle simplifié.</strong>
    La taille et le nombre des pastilles ne sont pas à l’échelle et ne représentent
    pas le nombre réel de molécules contenues dans 200 mL. Les pastilles servent
    seulement à montrer que les molécules se réorganisent et qu’aucune matière ne disparaît.
  </div>

  <div class="legend">
    <span><i class="dot water"></i> molécule d’eau</span>
    <span><i class="dot alcohol"></i> molécule d’alcool</span>
  </div>

  <div class="activity-title">État initial séparé → construis l’état final mélangé</div>

  <div class="final-area">

    <div class="tray">
      <h4>État initial — eau</h4>
      <p>18 pastilles bleues du modèle</p>
      <div class="pool" id="waterPool"></div>
    </div>

    <div class="center">
      <div class="final-label">État final — mélange eau + alcool</div>
      <div class="final-subtitle">Déplace toutes les pastilles dans ce récipient.</div>
      <div class="final-beaker-wrap">
        <div class="final-beaker" id="finalBeaker">
          <div class="bottom-zone"></div>
        </div>
      </div>
    </div>

    <div class="tray">
      <h4>État initial — alcool</h4>
      <p>4 pastilles orange du modèle</p>
      <div class="pool" id="alcoholPool"></div>
    </div>

  </div>

  <div class="controls">
    <button id="resetWater">↻ Remettre l’eau</button>
    <button id="resetAlcohol">↻ Remettre l’alcool</button>
    <button id="resetAll">↻ Tout remettre</button>
    <button class="primary" id="check">Vérifier mon modèle</button>
  </div>

  <div id="feedback" class="feedback neutral">
    Place les 22 pastilles dans le récipient final, puis vérifie ton modèle.
  </div>

</div>

<script>
(function(){
  const NW=18, NA=4;
  let generation=0, storageId="prototype", initialized=false, drag=null;
  let state=fresh();

  function fresh(){
    return {
      water:Array(NW).fill(null),
      alcohol:Array(NA).fill(null),
      errors:0,
      success:false
    };
  }

  function storageKey(){
    return "ludo_ex6_symbolic_v8_"+storageId+"_"+String(generation);
  }

  function save(){
    try{
      sessionStorage.setItem(storageKey(),JSON.stringify(state));
    }catch(e){}
  }

  function load(){
    try{
      const raw=sessionStorage.getItem(storageKey());
      if(!raw)return fresh();
      const p=JSON.parse(raw);
      return {
        water:Array.from({length:NW},(_,i)=>p.water?.[i]??null),
        alcohol:Array.from({length:NA},(_,i)=>p.alcohol?.[i]??null),
        errors:Number(p.errors||0),
        success:Boolean(p.success)
      };
    }catch(e){
      return fresh();
    }
  }

  function ready(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:componentReady",
      apiVersion:1
    },"*");
  }

  function height(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setFrameHeight",
      height:document.documentElement.scrollHeight+8
    },"*");
  }

  function send(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setComponentValue",
      value:{
        success:state.success,
        errors:state.errors,
        water_positions:state.water.filter(Boolean),
        alcohol_positions:state.alcohol.filter(Boolean)
      }
    },"*");
  }

  function makeParticle(type,index,placed){
    const e=document.createElement("div");
    e.className="particle "+type+" "+(placed?"placed":"source");
    e.dataset.type=type;
    e.dataset.index=String(index);
    e.id=(placed?"placed-":"source-")+type+"-"+index;
    e.addEventListener("pointerdown",startDrag);
    return e;
  }

  function source(type,i){
    return document.getElementById("source-"+type+"-"+i);
  }

  function placed(type,i){
    return document.getElementById("placed-"+type+"-"+i);
  }

  function build(){
    const wp=document.getElementById("waterPool");
    const ap=document.getElementById("alcoholPool");
    const beaker=document.getElementById("finalBeaker");

    wp.innerHTML="";
    ap.innerHTML="";
    beaker.querySelectorAll(".particle").forEach(e=>e.remove());

    for(let i=0;i<NW;i++){
      wp.appendChild(makeParticle("water",i,false));
      beaker.appendChild(makeParticle("water",i,true));
    }

    for(let i=0;i<NA;i++){
      ap.appendChild(makeParticle("alcohol",i,false));
      beaker.appendChild(makeParticle("alcohol",i,true));
    }

    renderAll();
    renderFeedback();
    setTimeout(height,40);
  }

  function renderOne(type,i){
    const pos=state[type][i];
    const s=source(type,i);
    const p=placed(type,i);

    if(pos){
      s.style.visibility="hidden";
      p.style.display="block";
      p.style.left=pos.x+"px";
      p.style.top=pos.y+"px";
    }else{
      s.style.visibility="visible";
      p.style.display="none";
    }
  }

  function renderAll(){
    for(let i=0;i<NW;i++)renderOne("water",i);
    for(let i=0;i<NA;i++)renderOne("alcohol",i);
  }

  function startDrag(e){
    e.preventDefault();

    const el=e.currentTarget;
    const rect=el.getBoundingClientRect();

    const ghost=el.cloneNode(true);
    ghost.removeAttribute("id");
    ghost.className="particle "+el.dataset.type+" ghost";
    ghost.style.left=rect.left+"px";
    ghost.style.top=rect.top+"px";
    document.body.appendChild(ghost);

    drag={
      type:el.dataset.type,
      index:Number(el.dataset.index),
      ghost,
      pointerId:e.pointerId,
      offsetX:e.clientX-rect.left,
      offsetY:e.clientY-rect.top
    };

    document.addEventListener("pointermove",move,{passive:false});
    document.addEventListener("pointerup",drop,{passive:false});
    document.addEventListener("pointercancel",cancel,{passive:false});
  }

  function move(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    e.preventDefault();

    drag.ghost.style.left=(e.clientX-drag.offsetX)+"px";
    drag.ghost.style.top=(e.clientY-drag.offsetY)+"px";
  }

  function cleanup(){
    if(drag?.ghost?.parentNode)drag.ghost.remove();

    document.removeEventListener("pointermove",move);
    document.removeEventListener("pointerup",drop);
    document.removeEventListener("pointercancel",cancel);
  }

  function cancel(){
    cleanup();
    drag=null;
  }

  function particleSize(type){
    return type==="water" ? 22 : 60;
  }

  function drop(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    e.preventDefault();

    const b=document.getElementById("finalBeaker");
    const br=b.getBoundingClientRect();

    const inside=
      e.clientX>=br.left&&e.clientX<=br.right&&
      e.clientY>=br.top&&e.clientY<=br.bottom;

    if(inside){
      const gr=drag.ghost.getBoundingClientRect();
      const size=particleSize(drag.type);

      let x=gr.left-br.left;
      let y=gr.top-br.top;

      x=Math.max(4,Math.min(b.clientWidth-size-4,x));
      y=Math.max(5,Math.min(b.clientHeight-size-5,y));

      state[drag.type][drag.index]={
        x:Math.round(x*10)/10,
        y:Math.round(y*10)/10
      };

      state.success=false;
      renderOne(drag.type,drag.index);
      save();
    }

    cleanup();
    drag=null;
  }

  function centre(point,type){
    const s=particleSize(type);
    return {
      x:point.x+s/2,
      y:point.y+s/2
    };
  }

  function nearestDistance(point,pointType,others,otherType){
    const p=centre(point,pointType);
    let d=Infinity;

    others.forEach(o=>{
      const q=centre(o,otherType);
      d=Math.min(d,Math.hypot(p.x-q.x,p.y-q.y));
    });

    return d;
  }

  function validate(){
    const w=state.water.filter(Boolean);
    const a=state.alcohol.filter(Boolean);

    state.success=false;

    if(w.length<NW||a.length<NA){
      state.errors++;
      setFeedback(
        "hint",
        "💡 Toutes les pastilles de l’état initial doivent se retrouver dans l’état final."
      );
      save();
      send();
      return;
    }

    const all=[
      ...w.map(p=>({p,type:"water"})),
      ...a.map(p=>({p,type:"alcohol"}))
    ];

    const centres=all.map(x=>centre(x.p,x.type));
    const ys=centres.map(p=>p.y);

    const occupiedHeight=Math.max(...ys)-Math.min(...ys);
    const meanY=ys.reduce((x,y)=>x+y,0)/ys.length;

    // Les deux espèces doivent être réellement mélangées :
    // une majorité de chaque espèce doit avoir un voisin de l'autre espèce.
    const waterNearAlcohol=
      w.filter(p=>nearestDistance(p,"water",a,"alcohol")<=82).length/NW;

    const alcoholNearWater=
      a.filter(p=>nearestDistance(p,"alcohol",w,"water")<=82).length/NA;

    // Le modèle représente un liquide : les molécules restent regroupées
    // dans une zone plutôt basse du récipient, sans exiger un niveau précis.
    const compact=
      occupiedHeight<=215 &&
      meanY>=138;

    const mixed=
      waterNearAlcohol>=0.42 &&
      alcoholNearWater>=0.75;

    if(compact&&mixed){
      state.success=true;
      setFeedback(
        "good",
        "✅ Ton modèle est cohérent : les deux sortes de molécules sont mélangées et toutes les pastilles de départ sont conservées."
      );
    }else{
      state.errors++;

      if(state.errors===1){
        setFeedback(
          "hint",
          "💡 Ton état final n’est pas encore convaincant. Observe si les deux sortes de molécules sont réellement mélangées."
        );
      }else if(state.errors===2){
        setFeedback(
          "hint",
          "💡 Vérifie aussi que les molécules restent regroupées comme dans un liquide et que toutes les pastilles de départ sont présentes."
        );
      }else{
        setFeedback(
          "hint",
          "💡 Dans l’état final, les deux espèces doivent être mélangées, proches et désordonnées. Aucune pastille ne doit disparaître."
        );
      }
    }

    save();
    send();
  }

  function setFeedback(kind,msg){
    const e=document.getElementById("feedback");
    e.className="feedback "+kind;
    e.textContent=msg;
  }

  function renderFeedback(){
    if(state.success){
      setFeedback("good","✅ Modèle validé.");
    }else{
      setFeedback(
        "neutral",
        "Place les 22 pastilles dans le récipient final, puis vérifie ton modèle."
      );
    }
  }

  function resetType(type){
    state[type]=Array(type==="water"?NW:NA).fill(null);
    state.success=false;

    renderAll();
    save();
    send();

    setFeedback(
      "neutral",
      (type==="water"?"Molécules d’eau":"Molécules d’alcool")+
      " remises dans l’état initial."
    );
  }

  function resetAll(){
    state.water=Array(NW).fill(null);
    state.alcohol=Array(NA).fill(null);
    state.success=false;

    renderAll();
    save();
    send();

    setFeedback(
      "neutral",
      "Toutes les molécules ont été remises dans l’état initial."
    );
  }

  document.getElementById("resetWater")
    .addEventListener("click",()=>resetType("water"));

  document.getElementById("resetAlcohol")
    .addEventListener("click",()=>resetType("alcohol"));

  document.getElementById("resetAll")
    .addEventListener("click",resetAll);

  document.getElementById("check")
    .addEventListener("click",validate);

  window.addEventListener("message",event=>{
    const d=event.data||{};

    if(d.type==="streamlit:render"){
      const args=d.args||{};
      const ng=Number(args.generation||0);
      const ns=String(args.storage_id||"prototype");

      if(!initialized||ng!==generation||ns!==storageId){
        generation=ng;
        storageId=ns;
        state=load();
        build();
        initialized=true;
      }else{
        height();
      }
    }
  });

  ready();

  setTimeout(()=>{
    if(!initialized){
      generation=0;
      storageId="standalone";
      state=load();
      build();
      initialized=true;
    }
  },250);

})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex6_component_v8():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex6_symbolic_component_v8"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(EX6_MIXTURE_HTML, encoding="utf-8")
    return components.declare_component(
        "ex6_water_alcohol_symbolic_v8",
        path=str(component_dir),
    )


def render_ex6_model(generation):
    component = _ex6_component_v8()

    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )

    return component(
        generation=int(generation),
        storage_id=storage_id,
        key=f"ex6_symbolic_v8_{generation}",
        default={
            "success": False,
            "errors": 0,
            "water_positions": [],
            "alcohol_positions": [],
        },
    )


def _ex6_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex6_generation", 0))
    touched = 0
    for q in (1,2,3):
        if str(st.session_state.get(f"ex6_q{q}_{generation}", "")).strip():
            touched += 1

    model_state = st.session_state.get("ex6_model_state")
    if isinstance(model_state, dict):
        if model_state.get("water_positions") or model_state.get("alcohol_positions"):
            touched += 1

    if touched == 0:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    errors = sum(
        int(st.session_state.get(f"ex6_q{q}_errors", 0))
        for q in (1,2,3)
    )
    if isinstance(model_state, dict):
        errors += int(model_state.get("errors", 0) or 0)

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise6_water_alcohol_volume"
        and r.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise6_water_alcohol_volume",
        "resource_label": PILOT_CONTENTS["exercise6_water_alcohol_volume"]["label"],
        "chapter": PILOT_CONTENTS["exercise6_water_alcohol_volume"]["chapter"],
        "score_percent": None,
        "completed_items": touched,
        "total_items": 4,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise6_water_alcohol():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex6_"):
            st.session_state.pop(key, None)


def _ex6_start_new_attempt():
    _ex6_record_restart_if_needed()
    generation = int(st.session_state.get("ex6_generation", 0))
    reset_exercise6_water_alcohol()
    st.session_state["ex6_generation"] = generation + 1


def page_exercise6_water_alcohol_volume():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise6_water_alcohol_volume"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex6-box{
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
            padding:1.05rem 1.15rem;margin:.55rem 0 1rem;color:#324a68;
            line-height:1.6;font-size:1.12rem;
        }
        .ex6-box strong{
            font-size:1.16rem;
        }
        .ex6-question{
            background:#f8fafc;border:1px solid #e1e7f0;border-radius:15px;
            padding:1rem 1.1rem .55rem;margin:1rem 0;
        }
        .ex6-question h3{
            font-size:1.28rem !important;
            line-height:1.45 !important;
            margin-bottom:.85rem !important;
        }
        .ex6-feedback{
            border-radius:12px;padding:.82rem 1rem;margin:.5rem 0 .9rem;
            font-weight:700;line-height:1.45;font-size:1rem;
        }
        .ex6-ok{background:#eefaf2;border:1px solid #cdebd6;color:#24623a}
        .ex6-hint{background:#fff7e6;border:1px solid #f4d69b;color:#73541c}
        .ex6-correction{background:#fff1f1;border:1px solid #f0c8c8;color:#7b2c2c}
        div[data-testid="stTextArea"] textarea{
            font-size:1.15rem!important;line-height:1.55!important;padding:.8rem .9rem!important;
        }
        div[data-testid="stTextArea"] label{
            font-size:1.04rem!important;font-weight:700!important;
        }

        /* Lisibilité générale de l'exercice 6 */
        .section-title{
            font-size:1.65rem !important;
            line-height:1.35 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Le mystère du volume perdu</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🧪 Exercice 6 — Le mystère du volume perdu : eau + alcool</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ex6-box"><strong>Objectif :</strong> raisonner sur la taille des molécules '
        'et la conservation de la masse.<br><br>'
        'Au laboratoire, un élève mélange <strong>200 mL d’eau liquide</strong> et '
        '<strong>200 mL d’alcool liquide</strong>. À sa grande surprise, le volume final '
        'mesuré est de <strong>380 mL</strong> au lieu de 400 mL. En revanche, la masse '
        'mesurée sur la balance n’a pas changé.</div>',
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex6_generation", 0))

    # Question 1
    st.markdown('<div class="ex6-question">', unsafe_allow_html=True)
    st.markdown(
        "### 1. Analogie : si tu mélanges un verre rempli de grosses billes et un verre "
        "rempli de sable fin, le volume total sera-t-il égal à la somme des deux verres ? Explique."
    )
    st.text_area(
        "Ta réponse",
        key=f"ex6_q1_{generation}",
        height=110,
        placeholder="Explique ce qui peut se passer entre les grosses billes et les grains de sable.",
        disabled=bool(st.session_state.get("ex6_q1_correct", False)),
        on_change=_ex6_clear_feedback,args=(1,),
    )
    st.button(
        "Valider la question 1",key="ex6_validate_q1",use_container_width=True,
        on_click=_ex6_validate_q1,disabled=bool(st.session_state.get("ex6_q1_correct", False)),
    )
    _ex6_feedback(1)
    st.markdown('</div>',unsafe_allow_html=True)

    # Question 2
    st.markdown('<div class="ex6-question">', unsafe_allow_html=True)
    st.markdown(
        "### 2. Interprétation microscopique : explique pourquoi, après le mélange, "
        "le volume obtenu est inférieur à 200 mL + 200 mL."
    )
    st.text_area(
        "Ta réponse",
        key=f"ex6_q2_{generation}",
        height=110,
        placeholder="Utilise l’analogie précédente pour raisonner à l’échelle des molécules.",
        disabled=bool(st.session_state.get("ex6_q2_correct", False)),
        on_change=_ex6_clear_feedback,args=(2,),
    )
    st.button(
        "Valider la question 2",key="ex6_validate_q2",use_container_width=True,
        on_click=_ex6_validate_q2,disabled=bool(st.session_state.get("ex6_q2_correct", False)),
    )
    _ex6_feedback(2)
    st.markdown('</div>',unsafe_allow_html=True)

    # Question 3
    st.markdown('<div class="ex6-question">', unsafe_allow_html=True)
    st.markdown(
        "### 3. Conservation de la masse : explique pourquoi la masse totale ne varie pas, "
        "alors que le volume final est inférieur à 400 mL."
    )
    st.text_area(
        "Ta réponse",
        key=f"ex6_q3_{generation}",
        height=110,
        placeholder="Réfléchis à ce qu’il advient des molécules pendant le mélange.",
        disabled=bool(st.session_state.get("ex6_q3_correct", False)),
        on_change=_ex6_clear_feedback,args=(3,),
    )
    st.button(
        "Valider la question 3",key="ex6_validate_q3",use_container_width=True,
        on_click=_ex6_validate_q3,disabled=bool(st.session_state.get("ex6_q3_correct", False)),
    )
    _ex6_feedback(3)
    st.markdown('</div>',unsafe_allow_html=True)

    # Question 4 interactive model
    st.markdown("### 4. Modélise l’état initial et l’état final")
    model_state = render_ex6_model(generation)
    if isinstance(model_state, dict):
        st.session_state["ex6_model_state"] = model_state
        q4_ok = bool(model_state.get("success"))
    else:
        q4_ok = False

    completed = (
        int(bool(st.session_state.get("ex6_q1_correct", False)))
        + int(bool(st.session_state.get("ex6_q2_correct", False)))
        + int(bool(st.session_state.get("ex6_q3_correct", False)))
        + int(q4_ok)
    )

    st.markdown("### Ton avancement")
    st.progress(completed/4)
    st.write(f"**{completed} / 4 parties réussies**")

    c_reset,_ = st.columns([1.4,4.6])
    with c_reset:
        if st.button("↻ Recommencer",key="restart_ex6",use_container_width=True):
            _ex6_start_new_attempt()
            st.rerun()

    if completed==4:
        st.success(
            "🎉 Bravo ! Tu as relié un volume final inférieur à la somme des volumes initiaux à l’organisation des molécules "
            "tout en conservant la même quantité de matière."
        )

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type")=="student"
            and student
            and not st.session_state.get("ex6_result_saved",False)
        ):
            model_errors = int(model_state.get("errors",0) or 0) if isinstance(model_state,dict) else 0
            total_errors = (
                int(st.session_state.get("ex6_q1_errors",0))
                + int(st.session_state.get("ex6_q2_errors",0))
                + int(st.session_state.get("ex6_q3_errors",0))
                + model_errors
            )
            score = round(100*4/max(4,4+total_errors))
            record_training_result(
                student,"exercise6_water_alcohol_volume",score,4,4,errors=total_errors
            )
            st.session_state["ex6_result_saved"]=True



# ============================================================
# EXERCICE 7 — LES MÉLANGES SOLIDES : LES ALLIAGES
# ============================================================

EXERCISE7_BRASS_IMAGE = "assets/chapitre_1/exercice 7/clé laiton.png"


def _ex7_normalize(value):
    value = str(value or "").strip().lower()
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "’": "'", "œ": "oe",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[^a-z0-9' ]+", " ", value)
    return " ".join(value.split())


def _ex7_clear_feedback(question):
    st.session_state.pop(f"ex7_q{question}_feedback", None)


def _ex7_q1_ok(value):
    v = _ex7_normalize(value)
    has_solid = "solide" in v
    has_mix = "melange" in v or "plusieurs" in v
    has_metal = "metal" in v or "metaux" in v or "element" in v
    return has_solid and has_mix and has_metal


def _ex7_q2_ok(answer, justification):
    a = _ex7_normalize(answer)
    j = _ex7_normalize(justification)
    mixture = "melange" in a
    mentions_metals = sum(
        term in j for term in ["cuivre", "zinc", "nickel"]
    ) >= 2
    several = any(x in j for x in [
        "plusieurs metaux", "trois metaux", "plusieurs elements",
        "plusieurs constituants", "differents metaux",
    ])
    return mixture and (mentions_metals or several)


def _ex7_q3_ok(value):
    v = _ex7_normalize(value)
    insertion = any(x in v for x in [
        "insertion", "s insere", "s inserent", "dans les espaces",
        "dans les interstices", "entre les atomes", "entre les gros atomes",
    ])
    substitution = any(x in v for x in [
        "substitution", "remplace", "remplacent", "prend la place",
        "prennent la place", "a la place",
    ])
    return insertion and substitution


def _ex7_q4_ok(brass, brass_justification, steel, steel_justification):
    """Valide le type d'alliage ET le raisonnement pour le laiton et l'acier."""
    b = _ex7_normalize(brass)
    bj = _ex7_normalize(brass_justification)
    s = _ex7_normalize(steel)
    sj = _ex7_normalize(steel_justification)

    brass_type_ok = "substitution" in b
    steel_type_ok = "insertion" in s

    brass_replace = any(x in bj for x in [
        "remplace", "remplacent", "remplacement",
        "prend la place", "prennent la place",
        "a la place", "substitue", "substituent",
    ])
    brass_atoms = any(x in bj for x in [
        "atome", "atomes", "cuivre", "zinc", "nickel", "metal", "metaux"
    ])
    brass_justification_ok = brass_replace and brass_atoms

    steel_carbon = any(x in sj for x in [
        "carbone", "petit atome", "petits atomes"
    ])
    steel_gap = any(x in sj for x in [
        "espace", "espaces", "interstice", "interstices",
        "entre les atomes", "entre les atomes de fer",
        "entre", "se glisse", "se glissent",
        "s insere", "s inserent",
    ])
    steel_structure = any(x in sj for x in [
        "fer", "reseau", "atome", "atomes"
    ])
    steel_justification_ok = steel_carbon and steel_gap and steel_structure

    return (
        brass_type_ok
        and steel_type_ok
        and brass_justification_ok
        and steel_justification_ok
    )


def _ex7_validate_q1():
    generation = int(st.session_state.get("ex7_generation", 0))
    value = st.session_state.get(f"ex7_q1_{generation}", "")
    if not str(value).strip():
        st.session_state["ex7_q1_feedback"] = "empty"
        return
    if _ex7_q1_ok(value):
        st.session_state["ex7_q1_correct"] = True
        st.session_state["ex7_q1_feedback"] = "correct"
    else:
        st.session_state["ex7_q1_correct"] = False
        st.session_state["ex7_q1_errors"] = int(st.session_state.get("ex7_q1_errors", 0)) + 1
        st.session_state["ex7_q1_feedback"] = "wrong"


def _ex7_validate_q2():
    generation = int(st.session_state.get("ex7_generation", 0))
    answer = st.session_state.get(f"ex7_q2_answer_{generation}", "")
    justification = st.session_state.get(f"ex7_q2_justification_{generation}", "")
    if not str(answer).strip() or not str(justification).strip():
        st.session_state["ex7_q2_feedback"] = "empty"
        return
    if _ex7_q2_ok(answer, justification):
        st.session_state["ex7_q2_correct"] = True
        st.session_state["ex7_q2_feedback"] = "correct"
    else:
        st.session_state["ex7_q2_correct"] = False
        st.session_state["ex7_q2_errors"] = int(st.session_state.get("ex7_q2_errors", 0)) + 1
        st.session_state["ex7_q2_feedback"] = "wrong"


def _ex7_validate_q3():
    generation = int(st.session_state.get("ex7_generation", 0))
    value = st.session_state.get(f"ex7_q3_{generation}", "")
    if not str(value).strip():
        st.session_state["ex7_q3_feedback"] = "empty"
        return
    if _ex7_q3_ok(value):
        st.session_state["ex7_q3_correct"] = True
        st.session_state["ex7_q3_feedback"] = "correct"
    else:
        st.session_state["ex7_q3_correct"] = False
        st.session_state["ex7_q3_errors"] = int(st.session_state.get("ex7_q3_errors", 0)) + 1
        st.session_state["ex7_q3_feedback"] = "wrong"


def _ex7_validate_q4():
    generation = int(st.session_state.get("ex7_generation", 0))

    brass = st.session_state.get(f"ex7_q4_brass_{generation}", "")
    brass_justification = st.session_state.get(
        f"ex7_q4_brass_justification_{generation}", ""
    )
    steel = st.session_state.get(f"ex7_q4_steel_{generation}", "")
    steel_justification = st.session_state.get(
        f"ex7_q4_steel_justification_{generation}", ""
    )

    if (
        not str(brass).strip()
        or not str(brass_justification).strip()
        or not str(steel).strip()
        or not str(steel_justification).strip()
    ):
        st.session_state["ex7_q4_feedback"] = "empty"
        return

    if _ex7_q4_ok(brass, brass_justification, steel, steel_justification):
        st.session_state["ex7_q4_correct"] = True
        st.session_state["ex7_q4_feedback"] = "correct"
    else:
        st.session_state["ex7_q4_correct"] = False
        st.session_state["ex7_q4_errors"] = (
            int(st.session_state.get("ex7_q4_errors", 0)) + 1
        )
        st.session_state["ex7_q4_feedback"] = "wrong"


def _ex7_feedback(question):
    feedback = st.session_state.get(f"ex7_q{question}_feedback")
    errors = int(st.session_state.get(f"ex7_q{question}_errors", 0))
    correct = bool(st.session_state.get(f"ex7_q{question}_correct", False))

    if correct:
        messages = {
            1: "✅ Bonne réponse ! Tu as identifié les éléments essentiels de la définition d’un alliage.",
            2: "✅ Bonne réponse ! Le laiton est bien un mélange solide de plusieurs métaux.",
            3: "✅ Bonne réponse ! Tu distingues correctement insertion et substitution.",
            4: "✅ Bonne réponse ! Tu as identifié les deux types d’alliages et justifié tes choix à partir de l’organisation des atomes.",
        }
        st.markdown(
            f'<div class="ex7-feedback ex7-ok">{messages[question]}</div>',
            unsafe_allow_html=True,
        )
        return

    if feedback == "empty":
        st.markdown(
            '<div class="ex7-feedback ex7-hint">✏️ Complète ta réponse avant de valider.</div>',
            unsafe_allow_html=True,
        )
        return

    if feedback != "wrong":
        return

    if question == 1:
        if errors == 1:
            msg = "💡 Relis le document : repère l’état physique du matériau et le nombre de constituants."
        elif errors == 2:
            msg = "📘 Un alliage n’est pas un métal pur : il contient plusieurs éléments et reste solide."
        else:
            msg = "🔎 Un alliage est un mélange homogène solide contenant plusieurs métaux, ou au moins un métal associé à un autre élément."

    elif question == 2:
        if errors == 1:
            msg = "💡 Observe la composition indiquée pour le laiton. Combien de métaux différents sont cités ?"
        elif errors == 2:
            msg = "📘 Un corps pur ne contient qu’une seule espèce chimique ; ici plusieurs métaux sont présents."
        else:
            msg = "🔎 Le laiton contient du cuivre, du zinc et du nickel : c’est donc un mélange."

    elif question == 3:
        if errors == 1:
            msg = "💡 Compare la position du nouvel atome dans les deux modèles : est-il entre les atomes ou à la place de l’un d’eux ?"
        elif errors == 2:
            msg = "📘 Dans un cas, de petits atomes occupent des espaces du réseau ; dans l’autre, certains atomes du réseau sont remplacés."
        else:
            msg = "🔎 Insertion : de petits atomes s’insèrent dans les espaces du cristal. Substitution : des atomes remplacent certains atomes du métal principal."

    else:
        if errors == 1:
            msg = (
                "💡 Relis le document 3 et explique, pour chacun des deux matériaux, "
                "où se placent les nouveaux atomes dans la structure."
            )
        elif errors == 2:
            msg = (
                "📘 Pour l’acier, observe le rôle des petits atomes de carbone. "
                "Pour le laiton, demande-toi ce que font les atomes métalliques "
                "de taille proche dans le réseau."
            )
        else:
            msg = (
                "🔎 Vérifie que ta justification contient bien ces idées : "
                "dans l’acier, de petits atomes se placent dans des espaces du réseau ; "
                "dans le laiton, certains atomes métalliques prennent la place d’autres atomes."
            )

    css = "ex7-hint" if errors < 3 else "ex7-correction"
    st.markdown(
        f'<div class="ex7-feedback {css}">{msg}</div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Schémas statiques : insertion / substitution
# ------------------------------------------------------------

EX7_STATIC_MODELS_HTML = r"""
<div class="alloy-models">
  <div class="alloy-card">
    <div class="alloy-title">Modèle A</div>
    <div class="lattice insertion">
      <span class="big b1"></span><span class="big b2"></span><span class="big b3"></span>
      <span class="big b4"></span><span class="big b5"></span><span class="big b6"></span>
      <span class="big b7"></span><span class="big b8"></span><span class="big b9"></span>
      <span class="small s1"></span><span class="small s2"></span><span class="small s3"></span>
    </div>
  </div>

  <div class="alloy-card">
    <div class="alloy-title">Modèle B</div>
    <div class="lattice substitution">
      <span class="big b1"></span><span class="big alt b2"></span><span class="big b3"></span>
      <span class="big b4"></span><span class="big b5"></span><span class="big alt2 b6"></span>
      <span class="big b7"></span><span class="big alt b8"></span><span class="big b9"></span>
    </div>
  </div>
</div>
"""


# ------------------------------------------------------------
# Module interactif : construire acier + laiton
# ------------------------------------------------------------

EX7_INTERACTIVE_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#17345f;background:#fff}
.wrap{max-width:1120px;margin:auto;padding:8px 10px 14px}
.intro{background:#f5f9ff;border:1px solid #cfe0fb;border-radius:14px;padding:11px 14px;margin-bottom:13px;line-height:1.45}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.panel{background:#f8fafc;border:1px solid #dce5f0;border-radius:16px;padding:14px}
.panel h3{text-align:center;margin:0 0 5px;color:#17345f}
.panel p{text-align:center;color:#64758a;font-size:12px;margin:0 0 10px}
.model{position:relative;width:320px;height:300px;margin:0 auto 12px;border:1px solid #d7e1ec;border-radius:16px;background:#fff}
.atom{position:absolute;border-radius:50%;box-shadow:0 2px 5px #0002}
.iron,.copper{width:48px;height:48px;border:3px solid}
.iron{background:#a6b5c4;border-color:#607385}
.copper{background:#e98b4a;border-color:#9c4f1f}
.zinc{width:48px;height:48px;background:#73c96e;border:3px solid #2b7c37}
.nickel{width:48px;height:48px;background:#8d79d8;border:3px solid #55419d}
.carbon{width:22px;height:22px;background:#2d3742;border:3px solid #111820}
.fixed{pointer-events:none}
.slot{display:none}
.interstice{position:absolute;width:28px;height:28px;border:2px dashed #aebed0;border-radius:50%;background:#f8fbff}
.interstice{transition:.15s ease}
.interstice:hover{background:#eef6ff;border-color:#7fa8d6}
.tray{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;min-height:62px;padding:8px;border:1px solid #dbe4ee;border-radius:12px;background:#fff}
.source{position:relative!important;left:auto!important;top:auto!important;cursor:grab;touch-action:none;user-select:none;flex:0 0 auto}
.placed{display:none;z-index:30;cursor:grab;touch-action:none;user-select:none}
.ghost{position:fixed!important;z-index:99999!important;pointer-events:none!important;transform:scale(1.06)}
.controls{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin:12px 0 8px}
button{border:1px solid #bfcde0;border-radius:11px;padding:9px 14px;font-weight:750;background:#fff;color:#17345f;cursor:pointer}
button.primary{background:#1f6fd6;border-color:#1b61b9;color:#fff}
.feedback{border-radius:12px;padding:10px 12px;font-weight:700;margin-top:8px;line-height:1.45}
.neutral{background:#f7f9fc;border:1px solid #dfe6ef;color:#6e7c90}
.good{background:#eaf8ef;border:1px solid #b8e2c4;color:#24623a}
.hint{background:#fff8e8;border:1px solid #efd89c;color:#73541c}
@media(max-width:850px){.grid{grid-template-columns:1fr}.model{width:300px}}
</style>
</head>
<body>
<div class="wrap">

<div class="intro">
  <strong>Construis les deux alliages.</strong>
  Pour l’acier, place les petits atomes de carbone dans les espaces du réseau de fer.
  Pour le laiton, dépose les atomes de zinc et de nickel directement sur des atomes de cuivre :
  l’atome orange sera alors remplacé.
</div>

<div class="grid">

  <div class="panel">
    <h3>Acier — alliage d’insertion</h3>
    <p>Réseau de fer + petits atomes de carbone</p>
    <div class="model" id="steelModel">
      <div class="interstice" style="left:90px;top:80px"></div>
      <div class="interstice" style="left:190px;top:80px"></div>
      <div class="interstice" style="left:140px;top:160px"></div>
      <div class="interstice" style="left:240px;top:160px"></div>
    </div>
    <div class="tray" id="carbonTray"></div>
  </div>

  <div class="panel">
    <h3>Laiton — alliage de substitution</h3>
    <p>Réseau de cuivre ordonné : remplace certains atomes orange</p>
    <div class="model" id="brassModel"></div>
    <div class="tray" id="brassTray"></div>
  </div>

</div>

<div class="controls">
  <button id="resetSteel">↻ Refaire l’acier</button>
  <button id="resetBrass">↻ Refaire le laiton</button>
  <button id="resetAll">↻ Tout recommencer</button>
  <button class="primary" id="check">Vérifier mes modèles</button>
</div>

<div id="feedback" class="feedback neutral">
  Construis les deux modèles puis vérifie.
</div>

</div>

<script>
(function(){
  const NC=4, NB=4;
  let generation=0,storageId="prototype",initialized=false,drag=null;

  const steelFixed=[
    [30,30],[110,30],[190,30],[270,30],
    [30,110],[110,110],[190,110],[270,110],
    [30,190],[110,190],[190,190],[270,190]
  ];

  const brassFixed=[
    [30,30],[100,30],[170,30],[240,30],
    [30,118],[100,118],[170,118],[240,118],
    [30,206],[100,206],[170,206],[240,206]
  ];

  const steelTargets=[[90,80],[190,80],[140,160],[240,160]];

  // Pour le laiton, chaque atome orange du réseau peut être substitué.
  // Les cibles correspondent donc exactement aux positions des atomes de cuivre.
  const brassTargets=[
    [30,30],[100,30],[170,30],[240,30],
    [30,118],[100,118],[170,118],[240,118],
    [30,206],[100,206],[170,206],[240,206]
  ];

  function fresh(){
    return{
      carbon:Array(NC).fill(null),
      brass:Array(NB).fill(null),
      errors:0,
      success:false
    };
  }

  let state=fresh();

  function storageKey(){return "ludo_ex7_alloys_v3_"+storageId+"_"+String(generation)}
  function save(){try{sessionStorage.setItem(storageKey(),JSON.stringify(state))}catch(e){}}
  function load(){
    try{
      const raw=sessionStorage.getItem(storageKey());
      if(!raw)return fresh();
      const p=JSON.parse(raw);
      return{
        carbon:Array.from({length:NC},(_,i)=>p.carbon?.[i]??null),
        brass:Array.from({length:NB},(_,i)=>p.brass?.[i]??null),
        errors:Number(p.errors||0),
        success:Boolean(p.success)
      };
    }catch(e){return fresh()}
  }

  function ready(){
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:componentReady",apiVersion:1},"*");
  }
  function height(){
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:setFrameHeight",height:document.documentElement.scrollHeight+8},"*");
  }
  function send(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setComponentValue",
      value:{
        success:state.success,
        errors:state.errors,
        carbon_positions:state.carbon.filter(Boolean),
        brass_positions:state.brass.filter(Boolean)
      }
    },"*");
  }

  function fixedAtom(cls,x,y,id=null){
    const e=document.createElement("div");
    e.className="atom "+cls+" fixed";
    e.style.left=x+"px";
    e.style.top=y+"px";
    if(id!==null)e.id=id;
    return e;
  }

  function draggable(type,index,placed){
    const e=document.createElement("div");
    let cls="atom ";
    if(type==="carbon")cls+="carbon ";
    else cls+=(index<2?"zinc ":"nickel ");
    cls+=(placed?"placed":"source");
    e.className=cls;
    e.dataset.type=type;
    e.dataset.index=String(index);
    e.id=(placed?"placed-":"source-")+type+"-"+index;
    e.addEventListener("pointerdown",startDrag);
    return e;
  }

  function source(type,i){return document.getElementById("source-"+type+"-"+i)}
  function placed(type,i){return document.getElementById("placed-"+type+"-"+i)}

  function build(){
    const steel=document.getElementById("steelModel");
    const brass=document.getElementById("brassModel");
    const carbonTray=document.getElementById("carbonTray");
    const brassTray=document.getElementById("brassTray");

    steel.querySelectorAll(".atom").forEach(e=>e.remove());
    brass.querySelectorAll(".atom").forEach(e=>e.remove());
    carbonTray.innerHTML="";
    brassTray.innerHTML="";

    steelFixed.forEach(p=>steel.appendChild(fixedAtom("iron",p[0],p[1])));
    brassFixed.forEach((p,i)=>{
      brass.appendChild(fixedAtom("copper",p[0],p[1],"copper-"+i));
    });

    for(let i=0;i<NC;i++){
      carbonTray.appendChild(draggable("carbon",i,false));
      steel.appendChild(draggable("carbon",i,true));
    }
    for(let i=0;i<NB;i++){
      brassTray.appendChild(draggable("brass",i,false));
      brass.appendChild(draggable("brass",i,true));
    }

    renderAll();
    renderFeedback();
    setTimeout(height,40);
  }

  function renderOne(type,i){
    const pos=state[type][i];
    const s=source(type,i),p=placed(type,i);
    if(pos){
      s.style.visibility="hidden";
      p.style.display="block";
      p.style.left=pos.x+"px";p.style.top=pos.y+"px";
    }else{
      s.style.visibility="visible";
      p.style.display="none";
    }
  }

  function renderBrassBase(){
    // Tous les atomes de cuivre sont visibles par défaut.
    brassFixed.forEach((_,i)=>{
      const e=document.getElementById("copper-"+i);
      if(e)e.style.visibility="visible";
    });

    // Quand un atome de zinc/nickel occupe une position du réseau,
    // l'atome de cuivre orange correspondant disparaît : vraie substitution.
    state.brass.forEach(pos=>{
      if(!pos || !Number.isInteger(pos.target))return;
      const e=document.getElementById("copper-"+pos.target);
      if(e)e.style.visibility="hidden";
    });
  }

  function renderAll(){
    for(let i=0;i<NC;i++)renderOne("carbon",i);
    for(let i=0;i<NB;i++)renderOne("brass",i);
    renderBrassBase();
  }

  function startDrag(e){
    e.preventDefault();
    const el=e.currentTarget,rect=el.getBoundingClientRect();
    const ghost=el.cloneNode(true);
    ghost.removeAttribute("id");
    ghost.classList.add("ghost");
    ghost.style.left=rect.left+"px";
    ghost.style.top=rect.top+"px";
    document.body.appendChild(ghost);

    drag={
      type:el.dataset.type,
      index:Number(el.dataset.index),
      ghost,
      pointerId:e.pointerId,
      offsetX:e.clientX-rect.left,
      offsetY:e.clientY-rect.top
    };

    document.addEventListener("pointermove",move,{passive:false});
    document.addEventListener("pointerup",drop,{passive:false});
    document.addEventListener("pointercancel",cancel,{passive:false});
  }

  function move(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    e.preventDefault();
    drag.ghost.style.left=(e.clientX-drag.offsetX)+"px";
    drag.ghost.style.top=(e.clientY-drag.offsetY)+"px";
  }

  function cleanup(){
    if(drag?.ghost?.parentNode)drag.ghost.remove();
    document.removeEventListener("pointermove",move);
    document.removeEventListener("pointerup",drop);
    document.removeEventListener("pointercancel",cancel);
  }

  function cancel(){cleanup();drag=null}

  function targetList(type){
    return type==="carbon" ? steelTargets : brassTargets;
  }

  function particleSize(type){
    return type==="carbon" ? 22 : 48;
  }

  function targetBoxSize(type){
    return type==="carbon" ? 28 : 48;
  }

  function snappedPosition(type,targetIndex){
    const targets=targetList(type);
    const t=targets[targetIndex];

    // Pour l'acier, on centre le petit carbone dans l'interstice pointillé.
    // Pour le laiton, la particule de substitution prend exactement
    // la place de l'atome orange de cuivre.
    const delta = type==="carbon"
      ? (targetBoxSize(type)-particleSize(type))/2
      : 0;

    return{
      x:Math.round(t[0]+delta),
      y:Math.round(t[1]+delta),
      target:targetIndex
    };
  }

  function usedTargets(type,ignoreIndex){
    const used=new Set();
    state[type].forEach((pos,i)=>{
      if(i===ignoreIndex||!pos)return;
      if(Number.isInteger(pos.target))used.add(pos.target);
    });
    return used;
  }

  function nearestAvailableTarget(type,index,clientX,clientY,modelRect){
    const targets=targetList(type);
    const occupied=usedTargets(type,index);
    const box=targetBoxSize(type);

    let best=null;
    let bestD=Infinity;

    targets.forEach((t,targetIndex)=>{
      if(occupied.has(targetIndex))return;

      const cx=modelRect.left+t[0]+box/2;
      const cy=modelRect.top+t[1]+box/2;
      const d=Math.hypot(clientX-cx,clientY-cy);

      if(d<bestD){
        bestD=d;
        best=targetIndex;
      }
    });

    // L'élève doit déposer près d'un cercle pointillé.
    // Le seuil reste assez généreux pour rendre le geste facile.
    const maxDistance=type==="carbon" ? 48 : 62;
    return best!==null && bestD<=maxDistance ? best : null;
  }

  function drop(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    e.preventDefault();

    const model=document.getElementById(
      drag.type==="carbon" ? "steelModel" : "brassModel"
    );
    const br=model.getBoundingClientRect();

    const inside=
      e.clientX>=br.left&&e.clientX<=br.right&&
      e.clientY>=br.top&&e.clientY<=br.bottom;

    if(inside){
      const targetIndex=nearestAvailableTarget(
        drag.type,
        drag.index,
        e.clientX,
        e.clientY,
        br
      );

      if(targetIndex!==null){
        // Aimantation exacte au centre de la cible.
        state[drag.type][drag.index]=snappedPosition(drag.type,targetIndex);
        state.success=false;
        renderOne(drag.type,drag.index);
        if(drag.type==="brass")renderBrassBase();
        save();

        setFeedback(
          "neutral",
          drag.type==="carbon"
            ? "Atome de carbone placé dans un interstice."
            : "Atome métallique placé sur un emplacement du réseau."
        );
      }else{
        // On ne laisse plus l'atome flotter n'importe où dans le schéma.
        setFeedback(
          "hint",
          drag.type==="carbon"
            ? "💡 Dépose l’atome de carbone sur l’un des petits cercles pointillés."
            : "💡 Dépose l’atome vert ou violet directement sur un atome orange du réseau."
        );
      }
    }else{
      setFeedback(
        "hint",
        drag.type==="carbon"
          ? "💡 Dépose l’atome à l’intérieur du modèle, sur un petit cercle pointillé."
          : "💡 Dépose l’atome dans le modèle du laiton, directement sur un atome orange."
      );
    }

    cleanup();
    drag=null;
  }

  function targetMatch(positions,type,targets,maxD){
    const occupied=positions
      .map(p=>Number.isInteger(p.target)?p.target:null)
      .filter(v=>v!==null);

    if(type==="carbon"){
      // Les 4 petits carbones doivent occuper les 4 interstices.
      return (
        positions.length===steelTargets.length &&
        occupied.length===steelTargets.length &&
        new Set(occupied).size===steelTargets.length
      );
    }

    // Pour le laiton, on accepte n'importe quels 4 atomes de cuivre substitués,
    // à condition qu'ils correspondent à 4 positions différentes du réseau.
    return (
      positions.length===NB &&
      occupied.length===NB &&
      new Set(occupied).size===NB &&
      occupied.every(i=>i>=0 && i<brassTargets.length)
    );
  }

  function validate(){
    const c=state.carbon.filter(Boolean);
    const b=state.brass.filter(Boolean);
    state.success=false;

    if(c.length<NC||b.length<NB){
      state.errors++;
      setFeedback("hint","💡 Place tous les atomes proposés dans les deux modèles.");
      save();send();return;
    }

    const steelOk=targetMatch(c,"carbon",steelTargets,34);
    const brassOk=targetMatch(b,"brass",brassTargets,38);

    if(steelOk&&brassOk){
      state.success=true;
      setFeedback("good","✅ Les deux modèles sont cohérents : les petits atomes de carbone sont insérés entre les atomes de fer, tandis que les atomes de zinc et de nickel ont remplacé des atomes de cuivre dans le laiton.");
    }else{
      state.errors++;
      if(state.errors===1){
        setFeedback("hint","💡 Compare les deux gestes : dans l’acier, le nouvel atome se place entre les atomes de fer ; dans le laiton, il doit remplacer un atome orange.");
      }else if(state.errors===2){
        setFeedback("hint","💡 Pour l’acier, place les petits carbones dans les interstices. Pour le laiton, dépose les atomes verts et violets directement sur des atomes orange.");
      }else{
        setFeedback("hint","💡 Acier : remplis les quatre interstices. Laiton : substitue quatre atomes orange du réseau par les deux atomes de zinc et les deux atomes de nickel.");
      }
    }

    save();send();
  }

  function setFeedback(kind,msg){
    const e=document.getElementById("feedback");
    e.className="feedback "+kind;e.textContent=msg;
  }

  function renderFeedback(){
    if(state.success)setFeedback("good","✅ Modèles validés.");
    else setFeedback("neutral","Construis les deux modèles puis vérifie.");
  }

  function resetType(type){
    state[type]=Array(type==="carbon"?NC:NB).fill(null);
    state.success=false;
    renderAll();
    save();
    send();
    setFeedback(
      "neutral",
      type==="carbon"
        ? "Modèle de l’acier remis à zéro."
        : "Modèle du laiton remis à zéro : tous les atomes de cuivre sont de nouveau visibles."
    );
  }

  function resetAll(){
    state=fresh();
    renderAll();save();send();
    setFeedback("neutral","Les deux modèles ont été remis à zéro.");
  }

  document.getElementById("resetSteel").addEventListener("click",()=>resetType("carbon"));
  document.getElementById("resetBrass").addEventListener("click",()=>resetType("brass"));
  document.getElementById("resetAll").addEventListener("click",resetAll);
  document.getElementById("check").addEventListener("click",validate);

  window.addEventListener("message",event=>{
    const d=event.data||{};
    if(d.type==="streamlit:render"){
      const args=d.args||{};
      const ng=Number(args.generation||0),ns=String(args.storage_id||"prototype");
      if(!initialized||ng!==generation||ns!==storageId){
        generation=ng;storageId=ns;state=load();build();initialized=true;
      }else height();
    }
  });

  ready();
  setTimeout(()=>{if(!initialized){generation=0;storageId="standalone";state=load();build();initialized=true}},250);
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex7_component_v3():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex7_alloys_component_v3"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(EX7_INTERACTIVE_HTML, encoding="utf-8")
    return components.declare_component(
        "ex7_alloys_models_v3",
        path=str(component_dir),
    )


def render_ex7_models(generation):
    component = _ex7_component_v3()
    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )
    return component(
        generation=int(generation),
        storage_id=storage_id,
        key=f"ex7_alloys_v3_{generation}",
        default={
            "success": False,
            "errors": 0,
            "carbon_positions": [],
            "brass_positions": [],
        },
    )


def _ex7_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex7_generation", 0))
    touched = 0

    keys = [
        f"ex7_q1_{generation}",
        f"ex7_q2_answer_{generation}",
        f"ex7_q2_justification_{generation}",
        f"ex7_q3_{generation}",
        f"ex7_q4_brass_{generation}",
        f"ex7_q4_brass_justification_{generation}",
        f"ex7_q4_steel_{generation}",
        f"ex7_q4_steel_justification_{generation}",
    ]
    if any(str(st.session_state.get(k, "")).strip() for k in keys):
        touched = 1

    model_state = st.session_state.get("ex7_model_state")
    if isinstance(model_state, dict):
        if model_state.get("carbon_positions") or model_state.get("brass_positions"):
            touched = 1

    if not touched:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    total_errors = sum(
        int(st.session_state.get(f"ex7_q{i}_errors", 0))
        for i in (1,2,3,4)
    )
    if isinstance(model_state, dict):
        total_errors += int(model_state.get("errors", 0) or 0)

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise7_solid_mixtures_alloys"
        and r.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise7_solid_mixtures_alloys",
        "resource_label": PILOT_CONTENTS["exercise7_solid_mixtures_alloys"]["label"],
        "chapter": PILOT_CONTENTS["exercise7_solid_mixtures_alloys"]["chapter"],
        "score_percent": None,
        "completed_items": 0,
        "total_items": 5,
        "errors": total_errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise7_alloys():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex7_"):
            st.session_state.pop(key, None)


def _ex7_start_new_attempt():
    _ex7_record_restart_if_needed()
    generation = int(st.session_state.get("ex7_generation", 0))
    reset_exercise7_alloys()
    st.session_state["ex7_generation"] = generation + 1


def page_exercise7_solid_mixtures_alloys():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise7_solid_mixtures_alloys"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex7-doc{
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
            padding:1rem 1.1rem;margin:.6rem 0 1rem;color:#314b69;
            line-height:1.55;font-size:1.08rem;
        }
        .ex7-doc h3{margin:.1rem 0 .55rem;color:#173b70}
        .ex7-question{
            background:#f8fafc;border:1px solid #e1e7f0;border-radius:15px;
            padding:1rem 1.1rem .55rem;margin:1rem 0;
        }
        .ex7-question h3{
            font-size:1.25rem!important;line-height:1.45!important;margin-bottom:.8rem!important;
        }
        .ex7-feedback{
            border-radius:12px;padding:.82rem 1rem;margin:.5rem 0 .9rem;
            font-weight:700;line-height:1.45;font-size:1rem;
        }
        .ex7-ok{background:#eefaf2;border:1px solid #cdebd6;color:#24623a}
        .ex7-hint{background:#fff7e6;border:1px solid #f4d69b;color:#73541c}
        .ex7-correction{background:#fff1f1;border:1px solid #f0c8c8;color:#7b2c2c}
        .alloy-models{
            display:grid;grid-template-columns:1fr 1fr;gap:24px;
            max-width:780px;margin:1rem auto;
        }
        .alloy-card{
            border:1px solid #dbe5ef;border-radius:16px;background:#fff;
            padding:12px;text-align:center;
        }
        .alloy-title{font-weight:900;margin-bottom:8px;color:#173b70}
        .lattice{position:relative;width:240px;height:220px;margin:auto}
        .lattice span{position:absolute;border-radius:50%}
        .big{
            width:54px;height:54px;background:#d58a50;border:3px solid #8c5127;
        }
        .big.alt{background:#79c96e;border-color:#2f7c39}
        .big.alt2{background:#8b79d5;border-color:#54429a}
        .small{
            width:22px;height:22px;background:#303943;border:3px solid #111820;
        }
        .b1{left:20px;top:20px}.b2{left:92px;top:20px}.b3{left:164px;top:20px}
        .b4{left:20px;top:92px}.b5{left:92px;top:92px}.b6{left:164px;top:92px}
        .b7{left:20px;top:164px}.b8{left:92px;top:164px}.b9{left:164px;top:164px}
        .s1{left:75px;top:76px}.s2{left:147px;top:76px}.s3{left:111px;top:148px}
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea{
            font-size:1.12rem!important;line-height:1.5!important;
        }
        @media(max-width:800px){.alloy-models{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Les alliages</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🔑 Exercice 7 — Les mélanges solides : les alliages</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="ex7-doc"><strong>Objectif :</strong> comprendre la structure microscopique '
        'd’un mélange de solides.<br><br>'
        'Après avoir étudié des mélanges liquides, on peut se demander si des solides peuvent '
        'eux aussi former des mélanges. C’est le cas de nombreux métaux utilisés dans la vie quotidienne.</div>',
        unsafe_allow_html=True,
    )

    # Document avec photo
    c_text, c_img = st.columns([1.8, 1], gap="large")
    with c_text:
        st.markdown(
            """
            <div class="ex7-doc">
              <h3>Document 1 — Qu’est-ce qu’un alliage ?</h3>
              Un <strong>alliage</strong> est un matériau solide constitué d’un
              <strong>mélange homogène de plusieurs éléments</strong>.
              Il contient au moins un métal.<br><br>
              On distingue notamment :
              <strong>les alliages d’insertion</strong> et
              <strong>les alliages de substitution</strong>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="ex7-doc">
              <h3>Document 2 — Exemple : le laiton</h3>
              Le laiton utilisé ici est présenté comme un alliage contenant
              <strong>du cuivre, du zinc et du nickel</strong>.<br><br>
              Les atomes de ces différents métaux ont des
              <strong>tailles relativement proches</strong>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_img:
        image_path = Path(EXERCISE7_BRASS_IMAGE)
        if image_path.exists():
            st.image(str(image_path), caption="Exemple d’objet en laiton", use_container_width=True)
        else:
            st.warning(
                "Image manquante : ajoute « clé laiton.png » dans "
                "assets/chapitre_1/exercice 7/."
            )

    generation = int(st.session_state.get("ex7_generation", 0))

    # Q1
    st.markdown('<div class="ex7-question">', unsafe_allow_html=True)
    st.markdown("### 1. Donne la définition d’un alliage.")
    st.text_area(
        "Ta réponse",
        key=f"ex7_q1_{generation}",
        height=100,
        placeholder="Rédige une définition en une phrase.",
        disabled=bool(st.session_state.get("ex7_q1_correct", False)),
        on_change=_ex7_clear_feedback,args=(1,),
    )
    st.button(
        "Valider la question 1",key="ex7_validate_q1",use_container_width=True,
        on_click=_ex7_validate_q1,disabled=bool(st.session_state.get("ex7_q1_correct", False)),
    )
    _ex7_feedback(1)
    st.markdown('</div>',unsafe_allow_html=True)

    # Q2
    st.markdown('<div class="ex7-question">', unsafe_allow_html=True)
    st.markdown("### 2. Le laiton est-il un corps pur ou un mélange ? Justifie à l’aide des documents.")
    st.text_input(
        "Ta réponse",
        key=f"ex7_q2_answer_{generation}",
        placeholder="Corps pur ou mélange ?",
        disabled=bool(st.session_state.get("ex7_q2_correct", False)),
        on_change=_ex7_clear_feedback,args=(2,),
    )
    st.text_area(
        "Ta justification",
        key=f"ex7_q2_justification_{generation}",
        height=95,
        placeholder="Appuie-toi sur la composition du laiton.",
        disabled=bool(st.session_state.get("ex7_q2_correct", False)),
        on_change=_ex7_clear_feedback,args=(2,),
    )
    st.button(
        "Valider la question 2",key="ex7_validate_q2",use_container_width=True,
        on_click=_ex7_validate_q2,disabled=bool(st.session_state.get("ex7_q2_correct", False)),
    )
    _ex7_feedback(2)
    st.markdown('</div>',unsafe_allow_html=True)

    # Modèles statiques
    st.markdown("### Document 3 — Les différents types d’alliages")
    st.markdown(
        """
        <div class="ex7-doc">
          <strong>Alliage d’insertion :</strong> de petits atomes d’un autre élément
          viennent <strong>s’insérer dans les espaces du réseau cristallin</strong>
          du métal principal. C’est le cas de l’<strong>acier</strong> :
          de petits atomes de carbone se placent entre les atomes de fer.<br><br>

          <strong>Alliage de substitution :</strong> certains atomes d’un autre élément,
          de taille comparable, <strong>remplacent des atomes du métal principal</strong>
          dans le réseau cristallin. Le <strong>laiton</strong> et le bronze sont des
          exemples d’alliages de substitution.<br><br>

          Dans les deux modèles ci-dessous, observe surtout
          <strong>la position des nouveaux atomes</strong>.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(EX7_STATIC_MODELS_HTML, unsafe_allow_html=True)

    # Q3
    st.markdown('<div class="ex7-question">', unsafe_allow_html=True)
    st.markdown("### 3. Explique la différence entre un alliage d’insertion et un alliage de substitution.")
    st.text_area(
        "Ta réponse",
        key=f"ex7_q3_{generation}",
        height=115,
        placeholder="Compare la position des nouveaux atomes dans les modèles A et B.",
        disabled=bool(st.session_state.get("ex7_q3_correct", False)),
        on_change=_ex7_clear_feedback,args=(3,),
    )
    st.button(
        "Valider la question 3",key="ex7_validate_q3",use_container_width=True,
        on_click=_ex7_validate_q3,disabled=bool(st.session_state.get("ex7_q3_correct", False)),
    )
    _ex7_feedback(3)
    st.markdown('</div>',unsafe_allow_html=True)

    # Q4
    st.markdown('<div class="ex7-question">', unsafe_allow_html=True)
    st.markdown(
        "### 4. À quel type d’alliage appartiennent le laiton et l’acier ? "
        "Justifie tes réponses."
    )

    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.markdown("#### Laiton")
        st.text_input(
            "Type d’alliage",
            key=f"ex7_q4_brass_{generation}",
            placeholder="Insertion ou substitution ?",
            disabled=bool(st.session_state.get("ex7_q4_correct", False)),
            on_change=_ex7_clear_feedback,
            args=(4,),
        )
        st.text_area(
            "Justification pour le laiton",
            key=f"ex7_q4_brass_justification_{generation}",
            height=105,
            placeholder=(
                "Explique ce que deviennent certains atomes du réseau "
                "lorsqu’on ajoute les autres métaux."
            ),
            disabled=bool(st.session_state.get("ex7_q4_correct", False)),
            on_change=_ex7_clear_feedback,
            args=(4,),
        )

    with c2:
        st.markdown("#### Acier")
        st.text_input(
            "Type d’alliage",
            key=f"ex7_q4_steel_{generation}",
            placeholder="Insertion ou substitution ?",
            disabled=bool(st.session_state.get("ex7_q4_correct", False)),
            on_change=_ex7_clear_feedback,
            args=(4,),
        )
        st.text_area(
            "Justification pour l’acier",
            key=f"ex7_q4_steel_justification_{generation}",
            height=105,
            placeholder=(
                "Explique où se placent les petits atomes de carbone "
                "par rapport aux atomes de fer."
            ),
            disabled=bool(st.session_state.get("ex7_q4_correct", False)),
            on_change=_ex7_clear_feedback,
            args=(4,),
        )

    st.button(
        "Valider la question 4",
        key="ex7_validate_q4",
        use_container_width=True,
        on_click=_ex7_validate_q4,
        disabled=bool(st.session_state.get("ex7_q4_correct", False)),
    )
    _ex7_feedback(4)
    st.markdown('</div>', unsafe_allow_html=True)

    # Construction interactive
    st.markdown("### 5. Construis les deux modèles pour vérifier ta compréhension")
    model_state = render_ex7_models(generation)
    if isinstance(model_state, dict):
        st.session_state["ex7_model_state"] = model_state
        q5_ok = bool(model_state.get("success"))
    else:
        q5_ok = False

    completed = (
        int(bool(st.session_state.get("ex7_q1_correct", False)))
        + int(bool(st.session_state.get("ex7_q2_correct", False)))
        + int(bool(st.session_state.get("ex7_q3_correct", False)))
        + int(bool(st.session_state.get("ex7_q4_correct", False)))
        + int(q5_ok)
    )

    st.markdown("### Ton avancement")
    st.progress(completed/5)
    st.write(f"**{completed} / 5 parties réussies**")

    c_reset,_=st.columns([1.4,4.6])
    with c_reset:
        if st.button("↻ Recommencer",key="restart_ex7",use_container_width=True):
            _ex7_start_new_attempt()
            st.rerun()

    if completed==5:
        st.success(
            "🎉 Bravo ! Tu sais maintenant reconnaître un alliage et distinguer insertion et substitution."
        )

        student=st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type")=="student"
            and student
            and not st.session_state.get("ex7_result_saved",False)
        ):
            model_errors = int(model_state.get("errors",0) or 0) if isinstance(model_state,dict) else 0
            total_errors = sum(
                int(st.session_state.get(f"ex7_q{i}_errors",0))
                for i in (1,2,3,4)
            ) + model_errors

            score = round(100*5/max(5,5+total_errors))
            record_training_result(
                student,
                "exercise7_solid_mixtures_alloys",
                score,
                5,
                5,
                errors=total_errors,
            )
            st.session_state["ex7_result_saved"]=True



# ============================================================
# EXERCICE 8 — SYMBOLES DES ÉLÉMENTS
# ============================================================

EXERCISE8_PERIODIC_TABLE_CANDIDATES = [
    Path("assets/chapitre_1/exercice_8/Tableau_periodique_des_elements.pdf"),
    Path("assets/chapitre_1/exercice 8/Tableau_periodique_des_elements.pdf"),
    Path("assets/chapitre_1/exercice_8/tableau_periodique.pdf"),
]

EXERCISE8_ROWS = [
    {"prompt_type": "name", "prompt": "Carbone", "answer": "C"},
    {"prompt_type": "name", "prompt": "Oxygène", "answer": "O"},
    {"prompt_type": "symbol", "prompt": "H", "answer": "Hydrogène"},
    {"prompt_type": "name", "prompt": "Néon", "answer": "Ne"},
    {"prompt_type": "name", "prompt": "Cobalt", "answer": "Co"},
    {"prompt_type": "symbol", "prompt": "N", "answer": "Azote"},
    {"prompt_type": "symbol", "prompt": "Hg", "answer": "Mercure"},
    {"prompt_type": "name", "prompt": "Argent", "answer": "Ag"},
    {"prompt_type": "symbol", "prompt": "Au", "answer": "Or"},
    {"prompt_type": "name", "prompt": "Tungstène", "answer": "W"},
]


def _ex8_norm(value):
    value = str(value or "").strip().lower()
    repl = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i", "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u", "ç": "c",
        "’": "'", "œ": "oe",
    }
    for old, new in repl.items():
        value = value.replace(old, new)
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", value).split())


def _ex8_find_periodic_table():
    for candidate in EXERCISE8_PERIODIC_TABLE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None



EX8_INTERACTIVE_TABLE_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  color:#17345f;
  background:#fff;
}
.wrap{width:100%;padding:2px 0 8px}
.help{
  margin:0 0 10px;
  padding:9px 12px;
  border:1px solid #cfe0fb;
  border-radius:12px;
  background:#f5f9ff;
  color:#4c6481;
  font-size:13px;
  line-height:1.4;
}
.grid{
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr) 118px;
  gap:8px;
  align-items:stretch;
}
.header{
  min-height:42px;
  display:flex;
  align-items:center;
  padding:0 14px;
  border-radius:10px;
  background:#173b70;
  color:#fff;
  font-weight:800;
  font-size:14px;
}
.header.help-head{justify-content:center}
.cell{
  min-height:72px;
  border-radius:12px;
  display:flex;
  align-items:center;
}
.fixed{
  border:1px solid #d7e1ec;
  background:#f8fafc;
  padding:8px 14px;
}
.fixed-inner{line-height:1.25}
.fixed-label{
  display:block;
  color:#718096;
  font-size:11px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:.03em;
  margin-bottom:4px;
}
.fixed-value{
  display:block;
  color:#17345f;
  font-size:17px;
  font-weight:750;
}
.answer{
  position:relative;
  border:2px solid #78b5ef;
  background:#edf6ff;
  transition:background .15s ease,border-color .15s ease,box-shadow .15s ease;
}
.answer.correct{
  background:#e9f8ee;
  border-color:#67bf80;
}
.answer.wrong{
  background:#fff0f0;
  border-color:#e57575;
}
.answer:focus-within{
  box-shadow:0 0 0 3px rgba(59,130,246,.12);
}
.answer{
  padding-bottom:18px;
}
.answer input{
  width:100%;
  height:52px;
  border:0;
  outline:0;
  background:transparent;
  padding:0 44px 0 14px;
  color:#17345f;
  font-size:17px;
  font-weight:650;
}
.answer input::placeholder{color:#7c94ad;font-weight:500}
.status{
  position:absolute;
  right:13px;
  top:50%;
  transform:translateY(-50%);
  font-size:18px;
  font-weight:900;
  pointer-events:none;
}
.answer.correct .status::after{content:"✓";color:#258343}
.answer.wrong .status::after{content:"✕";color:#c34242}
.correction{
  position:absolute;
  left:14px;
  right:38px;
  bottom:4px;
  min-height:14px;
  font-size:11px;
  line-height:1.2;
  font-weight:800;
  color:#b23a3a;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.answer:not(.wrong) .correction{display:none}
.table-btn{
  width:100%;
  min-height:72px;
  border:1px solid #a9c8eb;
  border-radius:12px;
  background:#fff;
  color:#175aa8;
  font-weight:800;
  font-size:13px;
  cursor:pointer;
  transition:.15s ease;
}
.table-btn:hover{background:#eef6ff;border-color:#6ea7df}
.progress{
  margin-top:11px;
  padding:9px 12px;
  border-radius:11px;
  background:#f7f9fc;
  border:1px solid #e0e6ee;
  color:#61738b;
  font-size:13px;
  font-weight:700;
}
.progress.done{
  background:#eaf8ef;
  border-color:#b8e2c4;
  color:#24623a;
}

@media(max-width:700px){
  .grid{
    grid-template-columns:minmax(0,1fr) minmax(0,1fr) 70px;
    gap:6px;
  }
  .header{padding:0 9px;font-size:12px}
  .cell,.table-btn{min-height:66px}
  .fixed{padding:7px 9px}
  .fixed-value,.answer input{font-size:15px}
  .fixed-label{font-size:9px}
  .table-btn{font-size:0}
  .table-btn::before{content:"🧪";font-size:21px}
  .modal{padding:5px}
  .modal-card{width:99vw;height:96vh;border-radius:11px}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="help">
    Complète chaque case bleue puis <strong>appuie sur Entrée</strong> ou passe à la case suivante.
    La case devient <strong>verte si la réponse est correcte</strong> et
    <strong>rouge si elle est incorrecte</strong>. Une fois corrigée, la réponse est
    <strong>verrouillée</strong> : seul « Recommencer » permet de refaire l’exercice.
  </div>

  <div class="grid" id="tableGrid">
    <div class="header">Élément</div>
    <div class="header">Symbole</div>
    <div class="header help-head">Aide</div>
  </div>

  <div class="progress" id="progress">0 réponse correcte</div>
</div>

<script>
(function(){
  let initialized=false;
  let generation=0;
  let storageId="prototype";
  let rows=[];
  let pdfData="";
  let state={answers:[],statuses:[],errors:0,lastChecked:[]};

  function ready(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:componentReady",
      apiVersion:1
    },"*");
  }

  function setHeight(){
    const wrap=document.querySelector(".wrap");
    const h=wrap ? Math.ceil(wrap.getBoundingClientRect().height)+12 : 700;
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setFrameHeight",
      height:h
    },"*");
  }

  function storageKey(){
    return "ludo_ex8_table_v4_"+storageId+"_"+String(generation);
  }

  function fresh(){
    return{
      answers:Array(rows.length).fill(""),
      statuses:Array(rows.length).fill(""),
      errors:0,
      lastChecked:Array(rows.length).fill("")
    };
  }

  function save(){
    try{sessionStorage.setItem(storageKey(),JSON.stringify(state))}catch(e){}
  }

  function load(){
    try{
      const raw=sessionStorage.getItem(storageKey());
      if(!raw)return fresh();
      const p=JSON.parse(raw);
      return{
        answers:Array.from({length:rows.length},(_,i)=>p.answers?.[i]??""),
        statuses:Array.from({length:rows.length},(_,i)=>p.statuses?.[i]??""),
        errors:Number(p.errors||0),
        lastChecked:Array.from({length:rows.length},(_,i)=>p.lastChecked?.[i]??"")
      };
    }catch(e){
      return fresh();
    }
  }

  function normalizeName(value){
    return String(value||"")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g,"")
      .replace(/œ/g,"oe")
      .replace(/[^a-z0-9 ]+/g," ")
      .replace(/\s+/g," ")
      .trim();
  }

  function isCorrect(row,value){
    if(row.prompt_type==="name"){
      // Pour un symbole chimique, la casse fait partie de la réponse.
      return String(value||"").trim()===String(row.answer||"").trim();
    }
    return normalizeName(value)===normalizeName(row.answer);
  }

  function send(){
    const correctCount=state.statuses.filter(x=>x==="correct").length;
    const answeredCount=state.statuses.filter(x=>x==="correct"||x==="wrong").length;
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setComponentValue",
      value:{
        success:correctCount===rows.length,
        complete:answeredCount===rows.length,
        correct_count:correctCount,
        answered_count:answeredCount,
        total:rows.length,
        errors:state.errors,
        answers:state.answers,
        statuses:state.statuses
      }
    },"*");
  }

  function fixedCell(label,value){
    const e=document.createElement("div");
    e.className="cell fixed";
    e.innerHTML=
      '<div class="fixed-inner">'+
      '<span class="fixed-label">'+label+'</span>'+
      '<span class="fixed-value">'+value+'</span>'+
      '</div>';
    return e;
  }

  function answerCell(row,index,placeholder){
    const box=document.createElement("div");
    box.className="cell answer";
    box.dataset.index=String(index);

    const input=document.createElement("input");
    input.type="text";
    input.autocomplete="off";
    input.spellcheck=false;
    input.placeholder=placeholder;
    input.value=state.answers[index]||"";
    input.setAttribute("aria-label",placeholder);

    const status=document.createElement("span");
    status.className="status";

    const correction=document.createElement("div");
    correction.className="correction";

    // Une réponse déjà validée (bonne ou fausse) est définitive.
    input.disabled=Boolean(state.statuses[index]);

    input.addEventListener("input",()=>{
      if(state.statuses[index])return;
      state.answers[index]=input.value;
      save();
      send();
    });

    input.addEventListener("keydown",(event)=>{
      if(event.key==="Enter"){
        event.preventDefault();
        validateOne(index,true);

        const inputs=[...document.querySelectorAll(".answer input")];
        const current=inputs.indexOf(input);
        const next=inputs.slice(current+1).find(el=>!el.disabled);
        if(next){
          next.focus();
          next.select();
        }else{
          input.blur();
        }
      }
    });

    input.addEventListener("change",()=>{
      if(!state.statuses[index])validateOne(index,true);
    });

    box.appendChild(input);
    box.appendChild(status);
    box.appendChild(correction);
    return box;
  }

  function tableButton(){
    const button=document.createElement("button");
    button.className="table-btn";
    button.type="button";
    button.innerHTML="🧪 Tableau";

    button.addEventListener("click",()=>{
      if(!pdfData){
        alert("Le tableau périodique n’est pas encore disponible dans les assets.");
        return;
      }

      try{
        const binary=atob(pdfData);
        const bytes=new Uint8Array(binary.length);
        for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);

        const blob=new Blob([bytes],{type:"application/pdf"});
        const url=URL.createObjectURL(blob);
        window.open(url,"_blank","noopener,noreferrer");
        setTimeout(()=>URL.revokeObjectURL(url),60000);
      }catch(e){
        alert("Impossible d’ouvrir le tableau périodique.");
      }
    });

    return button;
  }

  function updateCell(index){
    const box=document.querySelector('.answer[data-index="'+index+'"]');
    if(!box)return;

    box.classList.remove("correct","wrong");
    if(state.statuses[index])box.classList.add(state.statuses[index]);

    const input=box.querySelector("input");
    if(input)input.disabled=Boolean(state.statuses[index]);

    const correction=box.querySelector(".correction");
    if(correction){
      correction.textContent=
        state.statuses[index]==="wrong"
          ? "Correction : "+String(rows[index].answer||"")
          : "";
    }
  }

  function validateOne(index,countError){
    // Si la ligne a déjà été corrigée, on ne peut plus modifier le résultat.
    if(state.statuses[index])return;

    const value=String(state.answers[index]||"").trim();

    if(!value){
      return;
    }

    const ok=isCorrect(rows[index],value);

    if(ok){
      state.statuses[index]="correct";
    }else{
      state.statuses[index]="wrong";
      if(countError)state.errors+=1;
    }

    state.lastChecked[index]=value;
    updateCell(index);
    save();
    updateProgress();
    send();
  }

  function updateProgress(){
    const correct=state.statuses.filter(x=>x==="correct").length;
    const answered=state.statuses.filter(x=>x==="correct"||x==="wrong").length;
    const wrong=state.statuses.filter(x=>x==="wrong").length;
    const progress=document.getElementById("progress");

    if(answered===rows.length && rows.length){
      progress.className=wrong===0 ? "progress done" : "progress";
      progress.textContent=
        correct+" / "+rows.length+" réponse(s) correcte(s) • "+
        wrong+" erreur(s)";
    }else{
      progress.className="progress";
      progress.textContent=
        correct+" bonne(s) réponse(s) • "+
        answered+" / "+rows.length+" ligne(s) terminée(s)";
    }
  }

  function build(){
    const grid=document.getElementById("tableGrid");

    // garder uniquement les 3 en-têtes
    while(grid.children.length>3)grid.removeChild(grid.lastChild);

    rows.forEach((row,i)=>{
      if(row.prompt_type==="name"){
        grid.appendChild(fixedCell("Élément",row.prompt));
        grid.appendChild(answerCell(row,i,"Symbole"));
      }else{
        grid.appendChild(answerCell(row,i,"Nom de l’élément"));
        grid.appendChild(fixedCell("Symbole",row.prompt));
      }
      grid.appendChild(tableButton());
    });

    rows.forEach((_,i)=>updateCell(i));
    updateProgress();
    setTimeout(setHeight,50);
  }



  window.addEventListener("message",(event)=>{
    const d=event.data||{};
    if(d.type!=="streamlit:render")return;

    const args=d.args||{};
    const nextGeneration=Number(args.generation||0);
    const nextStorageId=String(args.storage_id||"prototype");
    const nextRows=Array.isArray(args.rows)?args.rows:[];
    const nextPdf=String(args.pdf_data||"");

    const changed=
      !initialized ||
      nextGeneration!==generation ||
      nextStorageId!==storageId ||
      JSON.stringify(nextRows)!==JSON.stringify(rows);

    generation=nextGeneration;
    storageId=nextStorageId;
    rows=nextRows;
    pdfData=nextPdf;

    if(changed){
      state=load();
      build();
      initialized=true;
    }else{
        setHeight();
    }
  });

  ready();
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex8_table_component_v4():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex8_table_component_v4"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(
        EX8_INTERACTIVE_TABLE_HTML,
        encoding="utf-8",
    )
    return components.declare_component(
        "ex8_interactive_periodic_table_v4",
        path=str(component_dir),
    )


def render_ex8_interactive_table(generation):
    component = _ex8_table_component_v4()

    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )

    periodic_path = _ex8_find_periodic_table()
    pdf_data = ""
    if periodic_path is not None:
        pdf_data = base64.b64encode(periodic_path.read_bytes()).decode("ascii")

    return component(
        generation=int(generation),
        storage_id=storage_id,
        rows=EXERCISE8_ROWS,
        pdf_data=pdf_data,
        key=f"ex8_interactive_table_v4_{generation}",
        default={
            "success": False,
            "complete": False,
            "correct_count": 0,
            "answered_count": 0,
            "total": len(EXERCISE8_ROWS),
            "errors": 0,
            "answers": [],
            "statuses": [],
        },
    )

def _ex8_render_periodic_table():
    path = _ex8_find_periodic_table()

    with st.expander("🧪 Consulter le tableau périodique", expanded=False):
        if path is None:
            st.warning(
                "Tableau périodique manquant. Ajoute le fichier "
                "« Tableau_periodique_des_elements.pdf » dans "
                "assets/chapitre_1/exercice_8/."
            )
            return

        pdf_bytes = path.read_bytes()
        encoded = base64.b64encode(pdf_bytes).decode("ascii")

        components.html(
            f"""
            <div style="border:1px solid #dbe5ef;border-radius:14px;overflow:hidden;">
              <iframe
                src="data:application/pdf;base64,{encoded}#toolbar=1&navpanes=0&view=FitH"
                style="width:100%;height:720px;border:0;background:white;">
              </iframe>
            </div>
            """,
            height=740,
            scrolling=False,
        )

        st.download_button(
            "📄 Ouvrir / télécharger le tableau périodique",
            data=pdf_bytes,
            file_name="Tableau_periodique_des_elements.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def _ex8_symbol_answer_ok(row, value):
    if row["prompt_type"] == "name":
        # Ici la casse du symbole est volontairement importante.
        return str(value or "").strip() == row["answer"]
    return _ex8_norm(value) == _ex8_norm(row["answer"])


def _ex8_validate_q1():
    generation = int(st.session_state.get("ex8_generation", 0))
    wrong = []
    missing = []

    for i, row in enumerate(EXERCISE8_ROWS):
        key = f"ex8_q1_{i}_{generation}"
        value = st.session_state.get(key, "")
        if not str(value).strip():
            missing.append(i)
        elif not _ex8_symbol_answer_ok(row, value):
            wrong.append(i)

    if missing:
        st.session_state["ex8_q1_feedback"] = {
            "kind": "empty",
            "missing": missing,
        }
        return

    if not wrong:
        st.session_state["ex8_q1_correct"] = True
        st.session_state["ex8_q1_feedback"] = {"kind": "correct"}
        return

    st.session_state["ex8_q1_correct"] = False
    st.session_state["ex8_q1_errors"] = int(
        st.session_state.get("ex8_q1_errors", 0)
    ) + 1
    st.session_state["ex8_q1_feedback"] = {
        "kind": "wrong",
        "wrong": wrong,
    }


def _ex8_q2_ok(value):
    """
    Accepte les formulations naturelles exprimant l'idée essentielle :
    plusieurs éléments peuvent commencer par la même lettre et une lettre
    supplémentaire permet de les distinguer.
    """
    v = _ex8_norm(value)

    distinction = any(x in v for x in [
        "disting", "differenc", "eviter confusion", "pas confond",
        "reconnaitre", "identifier",
    ])

    same_initial = any(x in v for x in [
        "meme lettre", "meme initial", "meme premiere lettre",
        "commence par la meme", "commencent par la meme",
        "plusieurs elements",
    ])

    second_letter = any(x in v for x in [
        "deuxieme lettre", "seconde lettre", "2e lettre",
        "deux lettres", "autre lettre",
        "la seconde", "la deuxieme",
        "seconde permet", "deuxieme permet",
    ])

    return distinction and (same_initial or second_letter)


def _ex8_validate_q2():
    generation = int(st.session_state.get("ex8_generation", 0))
    value = st.session_state.get(f"ex8_q2_{generation}", "")

    if not str(value).strip():
        st.session_state["ex8_q2_feedback"] = "empty"
        return

    if _ex8_q2_ok(value):
        st.session_state["ex8_q2_correct"] = True
        st.session_state["ex8_q2_feedback"] = "correct"
    else:
        st.session_state["ex8_q2_correct"] = False
        st.session_state["ex8_q2_errors"] = int(
            st.session_state.get("ex8_q2_errors", 0)
        ) + 1
        st.session_state["ex8_q2_feedback"] = "wrong"


def _ex8_q3_ok(value):
    v = _ex8_norm(value)
    return "wolfram" in v or "wolframium" in v


def _ex8_validate_q3():
    generation = int(st.session_state.get("ex8_generation", 0))
    value = st.session_state.get(f"ex8_q3_{generation}", "")

    if not str(value).strip():
        st.session_state["ex8_q3_feedback"] = "empty"
        return

    if _ex8_q3_ok(value):
        st.session_state["ex8_q3_correct"] = True
        st.session_state["ex8_q3_feedback"] = "correct"
    else:
        st.session_state["ex8_q3_correct"] = False
        st.session_state["ex8_q3_errors"] = int(
            st.session_state.get("ex8_q3_errors", 0)
        ) + 1
        st.session_state["ex8_q3_feedback"] = "wrong"


def _ex8_feedback_q1():
    feedback = st.session_state.get("ex8_q1_feedback")
    errors = int(st.session_state.get("ex8_q1_errors", 0))

    if not feedback:
        return

    kind = feedback.get("kind")

    if kind == "correct":
        st.success("✅ Toutes les correspondances sont correctes.")
        return

    if kind == "empty":
        st.warning("✏️ Complète toutes les cases avant de valider.")
        return

    wrong = feedback.get("wrong", [])

    if errors == 1:
        st.warning(
            f"💡 Il reste {len(wrong)} réponse(s) à revoir. "
            "Consulte le tableau périodique et vérifie aussi les majuscules/minuscules."
        )
    elif errors == 2:
        labels = []
        for i in wrong:
            row = EXERCISE8_ROWS[i]
            if row["prompt_type"] == "name":
                labels.append(row["prompt"])
            else:
                labels.append(f"symbole {row['prompt']}")
        st.warning(
            "🔎 Revois particulièrement : " + ", ".join(labels) + "."
        )
    else:
        corrections = []
        for i in wrong:
            row = EXERCISE8_ROWS[i]
            if row["prompt_type"] == "name":
                corrections.append(f"{row['prompt']} → {row['answer']}")
            else:
                corrections.append(f"{row['prompt']} → {row['answer']}")
        st.error(
            "📘 Vérifie ces correspondances puis corrige toi-même les cases : "
            + " ; ".join(corrections)
        )


def _ex8_feedback_text(question):
    feedback = st.session_state.get(f"ex8_q{question}_feedback")
    errors = int(st.session_state.get(f"ex8_q{question}_errors", 0))

    if feedback == "correct":
        if question == 2:
            st.success(
                "✅ Oui. Une deuxième lettre permet de distinguer des éléments "
                "qui ne peuvent pas tous utiliser la même lettre seule."
            )
        else:
            st.success(
                "✅ Bonne recherche : le symbole W est lié au nom « wolfram » "
                "(ou « wolframium »)."
            )
        return

    if feedback == "empty":
        st.warning("✏️ Rédige une réponse avant de valider.")
        return

    if feedback != "wrong":
        return

    if question == 2:
        if errors == 1:
            st.warning(
                "💡 Observe plusieurs noms d’éléments qui commencent par la même lettre."
            )
        elif errors == 2:
            st.warning(
                "🔎 Une seule lettre ne peut pas désigner deux éléments différents. "
                "Que peut-on ajouter pour les distinguer ?"
            )
        else:
            st.error(
                "📘 Certains symboles utilisent une deuxième lettre afin de "
                "distinguer des éléments ayant la même initiale."
            )
    else:
        if errors == 1:
            st.warning(
                "🔎 Ta réponse n’explique pas encore l’origine de la lettre W. "
                "Refais une recherche en t’intéressant à l’origine du symbole."
            )
        elif errors == 2:
            st.warning(
                "💡 Cherche si le tungstène possède ou a possédé un autre nom "
                "commençant par W."
            )
        else:
            st.error(
                "📘 Le symbole W est lié au nom « wolfram » / « wolframium ». "
                "Reformule maintenant cette idée avec tes propres mots."
            )


def _ex8_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex8_generation", 0))
    q1_state = st.session_state.get("ex8_q1_component_state") or {}
    touched = any(
        str(value).strip()
        for value in (q1_state.get("answers") or [])
    )
    touched = touched or bool(
        str(st.session_state.get(f"ex8_q2_{generation}", "")).strip()
        or str(st.session_state.get(f"ex8_q3_{generation}", "")).strip()
    )

    if not touched:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    total_errors = sum(
        int(st.session_state.get(f"ex8_q{i}_errors", 0))
        for i in (1, 2, 3)
    )

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise8_element_symbols"
        and r.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise8_element_symbols",
        "resource_label": PILOT_CONTENTS["exercise8_element_symbols"]["label"],
        "chapter": PILOT_CONTENTS["exercise8_element_symbols"]["chapter"],
        "score_percent": None,
        "completed_items": 0,
        "total_items": 3,
        "errors": total_errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise8():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex8_"):
            st.session_state.pop(key, None)


def _ex8_restart():
    _ex8_record_restart_if_needed()
    generation = int(st.session_state.get("ex8_generation", 0))
    reset_exercise8()
    st.session_state["ex8_generation"] = generation + 1


def page_exercise8_element_symbols():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise8_element_symbols"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex8-box{
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
            padding:1rem 1.1rem;margin:.7rem 0 1rem;font-size:1.08rem;
            line-height:1.55;color:#314b69;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea{
            font-size:1.12rem!important;line-height:1.5!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Symboles des éléments</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🧩 Exercice 8 — Symboles des éléments</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ex8-box"><strong>Objectif :</strong> utiliser le tableau périodique '
        'pour retrouver le nom ou le symbole d’un élément chimique.</div>',
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex8_generation", 0))

    st.markdown("### 1. Complète le tableau à l’aide de la classification périodique.")

    q1_state = render_ex8_interactive_table(generation)

    if isinstance(q1_state, dict):
        st.session_state["ex8_q1_component_state"] = q1_state

        q1_complete = bool(q1_state.get("complete"))
        q1_correct_count = int(q1_state.get("correct_count", 0) or 0)
        q1_total = int(q1_state.get("total", len(EXERCISE8_ROWS)) or len(EXERCISE8_ROWS))
        q1_errors = int(q1_state.get("errors", 0) or 0)

        # Pour l'avancement, une partie est terminée lorsque toutes ses lignes
        # ont été corrigées, même si le score n'est pas parfait.
        st.session_state["ex8_q1_correct"] = q1_complete
        st.session_state["ex8_q1_errors"] = q1_errors

        if q1_complete:
            if q1_correct_count == q1_total:
                st.success(
                    f"✅ Tableau terminé : {q1_correct_count} / {q1_total} bonnes réponses."
                )
            else:
                st.warning(
                    f"📊 Tableau terminé : {q1_correct_count} / {q1_total} bonnes réponses "
                    f"et {q1_errors} erreur(s). Les réponses corrigées restent verrouillées."
                )

    st.markdown(
        "### 2. Pourquoi certains symboles ont-ils deux lettres alors que d’autres n’en ont qu’une ?"
    )
    st.text_area(
        "Ta réponse",
        key=f"ex8_q2_{generation}",
        height=105,
        placeholder="Explique l’intérêt de la deuxième lettre.",
        disabled=bool(st.session_state.get("ex8_q2_correct", False)),
    )
    st.button(
        "Valider la question 2",
        key="ex8_validate_q2",
        use_container_width=True,
        on_click=_ex8_validate_q2,
        disabled=bool(st.session_state.get("ex8_q2_correct", False)),
    )
    _ex8_feedback_text(2)

    st.markdown("### 3. Pourquoi le symbole chimique du tungstène est-il W ?")
    st.info(
        "🌐 Fais une recherche libre sur Internet, puis reviens rédiger ta réponse. "
        "Aucun mot-clé de recherche ne t’est imposé."
    )

    search_col, spacer_col = st.columns([1.8, 4.2])
    with search_col:
        st.link_button(
            "🌐 Faire une recherche sur Internet ↗",
            "https://www.google.com/",
            use_container_width=True,
        )

    st.text_area(
        "Ta réponse après ta recherche",
        key=f"ex8_q3_{generation}",
        height=120,
        placeholder="Explique avec tes propres mots l’origine du symbole W.",
        disabled=bool(st.session_state.get("ex8_q3_correct", False)),
    )
    st.button(
        "Valider la question 3",
        key="ex8_validate_q3",
        use_container_width=True,
        on_click=_ex8_validate_q3,
        disabled=bool(st.session_state.get("ex8_q3_correct", False)),
    )
    _ex8_feedback_text(3)

    completed = sum(
        int(bool(st.session_state.get(f"ex8_q{i}_correct", False)))
        for i in (1, 2, 3)
    )
    st.markdown("### Ton avancement")
    st.progress(completed / 3)
    st.write(f"**{completed} / 3 parties réussies**")

    c_reset, _ = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex8",
            use_container_width=True,
        ):
            _ex8_restart()
            st.rerun()

    if completed == 3:
        st.success(
            "🎉 Bravo ! Tu sais retrouver des symboles dans le tableau périodique "
            "et expliquer l’origine particulière du symbole W."
        )

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex8_result_saved", False)
        ):
            q1_state_final = st.session_state.get("ex8_q1_component_state") or {}
            q1_correct_points = int(q1_state_final.get("correct_count", 0) or 0)
            q1_total_points = int(
                q1_state_final.get("total", len(EXERCISE8_ROWS))
                or len(EXERCISE8_ROWS)
            )

            q2_point = int(bool(st.session_state.get("ex8_q2_correct", False)))
            q3_point = int(bool(st.session_state.get("ex8_q3_correct", False)))

            earned_points = q1_correct_points + q2_point + q3_point
            total_points = q1_total_points + 2

            total_errors = sum(
                int(st.session_state.get(f"ex8_q{i}_errors", 0))
                for i in (1, 2, 3)
            )
            score = round(100 * earned_points / max(1, total_points))

            record_training_result(
                student,
                "exercise8_element_symbols",
                score,
                earned_points,
                total_points,
                errors=total_errors,
            )
            st.session_state["ex8_result_saved"] = True


# ============================================================
# EXERCICE 9 — ATOME OU MOLÉCULE ?
# ============================================================

EXERCISE9_ITEMS = [
    ("CO", "Molécule"),
    ("Co", "Atome"),
    ("CO₂", "Molécule"),
    ("H₂", "Molécule"),
    ("N", "Atome"),
    ("Fe", "Atome"),
    ("Cl₂", "Molécule"),
    ("Ne", "Atome"),
    ("C₆H₁₂O₆", "Molécule"),
    ("NH₃", "Molécule"),
    ("I₂", "Molécule"),
    ("H₂O₂", "Molécule"),
    ("NO₂", "Molécule"),
    ("Al", "Atome"),
    ("Cu", "Atome"),
    ("U", "Atome"),
]



EX9_INTERACTIVE_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  color:#17345f;
  background:#fff;
}
.wrap{width:100%;padding:2px 0 8px}
.help{
  background:#f5f9ff;
  border:1px solid #cfe0fb;
  border-radius:13px;
  padding:10px 13px;
  margin-bottom:10px;
  color:#4d6480;
  font-size:13px;
  line-height:1.45;
}
.row{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:8px;
  margin-bottom:8px;
}
.box{
  min-height:58px;
  border-radius:11px;
  border:1px solid #cfdbe9;
  background:#fff;
  display:flex;
  align-items:center;
  justify-content:center;
  text-align:center;
  font-weight:800;
  font-size:14px;
  color:#17345f;
}
.formula{
  background:#f8fafc;
  font-size:20px;
  font-weight:900;
}
.choice{
  cursor:pointer;
  transition:.15s ease;
}
.choice:hover:not(:disabled){
  background:#eef6ff;
  border-color:#7caee2;
}
.choice.correct{
  background:#e9f8ee;
  border-color:#62bb7a;
  color:#24623a;
}
.choice.wrong{
  background:#fff0f0;
  border-color:#e37272;
  color:#a93232;
}
.choice:disabled{cursor:default}
.counter{
  position:sticky;
  bottom:0;
  z-index:50;
  margin-top:10px;
  padding:11px 13px;
  border-radius:12px;
  background:#f7f9fc;
  border:1px solid #dfe6ef;
  font-weight:850;
  display:flex;
  justify-content:center;
  gap:30px;
  flex-wrap:wrap;
}
.counter.done{
  background:#eaf8ef;
  border-color:#b8e2c4;
  color:#24623a;
}
@media(max-width:700px){
  .row{grid-template-columns:repeat(3,minmax(0,1fr))}
  .box{min-height:54px;font-size:12px}
  .formula{font-size:18px}
  .counter{gap:14px;font-size:13px}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="help">
    Pour chaque écriture, clique une seule fois sur <strong>Atome</strong> ou
    <strong>Molécule</strong>. Le premier choix est définitif :
    <strong>vert</strong> = bonne réponse ; si tu te trompes, ton choix reste
    <strong>rouge</strong> et la bonne réponse apparaît en <strong>vert</strong>.
  </div>
  <div id="rows"></div>
  <div class="counter" id="counter">
    <span id="good">✅ Bonnes réponses : 0 / 0</span>
    <span id="errors">❌ Erreurs : 0</span>
  </div>
</div>

<script>
(function(){
  let initialized=false;
  let generation=0;
  let storageId="prototype";
  let items=[];
  let state={answered:[],correctFirstTry:[],selected:[],errors:0};

  function ready(){
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:componentReady",
      apiVersion:1
    },"*");
  }

  function setHeight(){
    const wrap=document.querySelector(".wrap");
    const h=wrap ? Math.ceil(wrap.getBoundingClientRect().height)+12 : 650;
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setFrameHeight",
      height:h
    },"*");
  }

  function storageKey(){
    return "ludo_ex9_click_v2_"+storageId+"_"+String(generation);
  }

  function fresh(){
    return{
      answered:Array(items.length).fill(false),
      correctFirstTry:Array(items.length).fill(false),
      selected:Array(items.length).fill(""),
      errors:0
    };
  }

  function load(){
    try{
      const raw=sessionStorage.getItem(storageKey());
      if(!raw)return fresh();
      const p=JSON.parse(raw);
      return{
        answered:Array.from({length:items.length},(_,i)=>Boolean(p.answered?.[i])),
        correctFirstTry:Array.from({length:items.length},(_,i)=>Boolean(p.correctFirstTry?.[i])),
        selected:Array.from({length:items.length},(_,i)=>String(p.selected?.[i]||"")),
        errors:Number(p.errors||0)
      };
    }catch(e){return fresh()}
  }

  function save(){
    try{sessionStorage.setItem(storageKey(),JSON.stringify(state))}catch(e){}
  }

  function send(){
    const answered=state.answered.filter(Boolean).length;
    const correct=state.correctFirstTry.filter(Boolean).length;
    window.parent.postMessage({
      isStreamlitMessage:true,
      type:"streamlit:setComponentValue",
      value:{
        success:answered===items.length,
        complete:answered===items.length,
        answered_count:answered,
        correct_count:correct,
        total:items.length,
        errors:state.errors,
        answered:state.answered,
        correct_first_try:state.correctFirstTry,
        selected:state.selected
      }
    },"*");
  }

  function choiceButton(index,label){
    const b=document.createElement("button");
    b.className="box choice";
    b.type="button";
    b.textContent=label;
    b.dataset.index=String(index);
    b.dataset.label=label;
    b.addEventListener("click",()=>choose(index,label));
    return b;
  }

  function formulaBox(formula){
    const d=document.createElement("div");
    d.className="box formula";
    d.innerHTML=formula;
    return d;
  }

  function choose(index,label){
    // Un seul choix possible : le premier clic est définitif.
    if(state.answered[index])return;

    const answer=items[index][1];
    state.answered[index]=true;
    state.selected[index]=label;

    if(label===answer){
      state.correctFirstTry[index]=true;
    }else{
      state.correctFirstTry[index]=false;
      state.errors+=1;
    }

    save();
    renderGroup(index);
    updateCounter();
    send();
  }

  function groupButtons(index){
    return [
      ...document.querySelectorAll(
        '.choice[data-index="'+index+'"]'
      )
    ];
  }

  function renderGroup(index){
    const answer=items[index][1];
    const answered=state.answered[index];
    const selected=state.selected[index];

    groupButtons(index).forEach(btn=>{
      const label=btn.dataset.label;
      btn.classList.remove("correct","wrong");

      if(answered){
        // Toujours montrer la bonne réponse en vert.
        if(label===answer){
          btn.classList.add("correct");
        }

        // Si le premier choix était faux, le montrer en rouge.
        if(selected && selected!==answer && label===selected){
          btn.classList.add("wrong");
        }
      }

      btn.disabled=answered;
    });
  }

  function updateCounter(){
    const answered=state.answered.filter(Boolean).length;
    const correct=state.correctFirstTry.filter(Boolean).length;

    document.getElementById("good").textContent=
      "✅ Bonnes réponses : "+correct+" / "+items.length;
    document.getElementById("errors").textContent=
      "❌ Erreurs : "+state.errors;

    const counter=document.getElementById("counter");
    counter.classList.toggle("done",answered===items.length && items.length>0);
  }

  function build(){
    const host=document.getElementById("rows");
    host.innerHTML="";

    for(let i=0;i<items.length;i+=2){
      const row=document.createElement("div");
      row.className="row";

      const first=items[i];
      row.appendChild(formulaBox(first[0]));
      row.appendChild(choiceButton(i,"Atome"));
      row.appendChild(choiceButton(i,"Molécule"));

      if(i+1<items.length){
        const second=items[i+1];
        row.appendChild(formulaBox(second[0]));
        row.appendChild(choiceButton(i+1,"Atome"));
        row.appendChild(choiceButton(i+1,"Molécule"));
      }else{
        for(let k=0;k<3;k++){
          const empty=document.createElement("div");
          empty.className="box";
          empty.style.visibility="hidden";
          row.appendChild(empty);
        }
      }

      host.appendChild(row);
    }

    items.forEach((_,i)=>renderGroup(i));
    updateCounter();
    setTimeout(setHeight,40);
  }

  window.addEventListener("message",(event)=>{
    const d=event.data||{};
    if(d.type!=="streamlit:render")return;

    const args=d.args||{};
    const ng=Number(args.generation||0);
    const ns=String(args.storage_id||"prototype");
    const nextItems=Array.isArray(args.items)?args.items:[];

    const changed=
      !initialized ||
      ng!==generation ||
      ns!==storageId ||
      JSON.stringify(nextItems)!==JSON.stringify(items);

    generation=ng;
    storageId=ns;
    items=nextItems;

    if(changed){
      state=load();
      build();
      initialized=true;
    }else{
      setHeight();
    }
  });

  ready();
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex9_component_v2():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex9_click_component_v2"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(
        EX9_INTERACTIVE_HTML,
        encoding="utf-8",
    )
    return components.declare_component(
        "ex9_atom_molecule_click_v2",
        path=str(component_dir),
    )


def render_ex9_interactive(generation):
    component = _ex9_component_v2()

    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )

    items = _ex9_order(generation)

    return component(
        generation=int(generation),
        storage_id=storage_id,
        items=items,
        key=f"ex9_atom_molecule_click_v2_{generation}",
        default={
            "success": False,
            "complete": False,
            "answered_count": 0,
            "correct_count": 0,
            "total": len(items),
            "errors": 0,
            "answered": [],
            "correct_first_try": [],
            "selected": [],
        },
    )

def _ex9_order(generation):
    items = list(EXERCISE9_ITEMS)
    rng = random.Random(9107 + int(generation))
    rng.shuffle(items)
    return items


def _ex9_validate():
    generation = int(st.session_state.get("ex9_generation", 0))
    items = _ex9_order(generation)

    missing = []
    wrong = []

    for i, (formula, answer) in enumerate(items):
        value = st.session_state.get(f"ex9_answer_{i}_{generation}")
        if not value:
            missing.append(i)
        elif value != answer:
            wrong.append(i)

    if missing:
        st.session_state["ex9_feedback"] = {
            "kind": "empty",
            "missing": missing,
        }
        return

    if not wrong:
        st.session_state["ex9_correct"] = True
        st.session_state["ex9_feedback"] = {"kind": "correct"}
        return

    st.session_state["ex9_correct"] = False
    st.session_state["ex9_errors"] = int(
        st.session_state.get("ex9_errors", 0)
    ) + 1
    st.session_state["ex9_feedback"] = {
        "kind": "wrong",
        "wrong": wrong,
    }


def _ex9_feedback():
    feedback = st.session_state.get("ex9_feedback")
    errors = int(st.session_state.get("ex9_errors", 0))
    generation = int(st.session_state.get("ex9_generation", 0))
    items = _ex9_order(generation)

    if not feedback:
        return

    if feedback["kind"] == "correct":
        st.success(
            "✅ Tout est correct. Tu distingues bien symbole d’un atome "
            "et formule d’une molécule."
        )
        return

    if feedback["kind"] == "empty":
        st.warning("✏️ Classe toutes les écritures avant de valider.")
        return

    wrong = feedback.get("wrong", [])

    if errors == 1:
        st.warning(
            f"💡 Il reste {len(wrong)} classement(s) à revoir. "
            "Regarde si l’écriture représente un seul symbole d’élément "
            "ou plusieurs atomes assemblés."
        )
    elif errors == 2:
        formulas = [items[i][0] for i in wrong]
        st.warning(
            "🔎 Revois particulièrement : " + ", ".join(formulas) + ". "
            "Attention : une majuscule ou une minuscule peut changer le sens."
        )
    else:
        details = []
        for i in wrong:
            formula, answer = items[i]
            if formula == "CO":
                details.append("CO : C et O → molécule")
            elif formula == "Co":
                details.append("Co : symbole du cobalt → atome")
            elif answer == "Atome":
                details.append(f"{formula} : un seul symbole d’élément → atome")
            else:
                details.append(f"{formula} : plusieurs atomes → molécule")

        st.error(
            "📘 Utilise ces indications puis corrige toi-même : "
            + " ; ".join(details)
        )


def _ex9_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex9_generation", 0))
    ex9_state = st.session_state.get("ex9_component_state") or {}
    touched = bool(
        ex9_state.get("correct_count")
        or ex9_state.get("errors")
    )
    if not touched:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise9_atom_or_molecule"
        and r.get("activity_kind") == "training"
    ]

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise9_atom_or_molecule",
        "resource_label": PILOT_CONTENTS["exercise9_atom_or_molecule"]["label"],
        "chapter": PILOT_CONTENTS["exercise9_atom_or_molecule"]["chapter"],
        "score_percent": None,
        "completed_items": 0,
        "total_items": len(EXERCISE9_ITEMS),
        "errors": int(st.session_state.get("ex9_errors", 0)),
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise9():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex9_"):
            st.session_state.pop(key, None)


def _ex9_restart():
    _ex9_record_restart_if_needed()
    generation = int(st.session_state.get("ex9_generation", 0))
    reset_exercise9()
    st.session_state["ex9_generation"] = generation + 1


def page_exercise9_atom_or_molecule():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise9_atom_or_molecule"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Atome ou molécule</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">⚛️ Exercice 9 — Atome ou molécule ?</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div style="
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:14px;
            padding:.9rem 1rem;margin:.7rem 0 1rem;font-size:1.06rem;
            line-height:1.5;color:#314b69;">
          <strong>Consigne :</strong> pour chaque écriture, indique s’il s’agit
          d’un <strong>atome</strong> ou d’une <strong>molécule</strong>.
          La correction est immédiate.
        </div>
        """,
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex9_generation", 0))
    state = render_ex9_interactive(generation)

    if isinstance(state, dict):
        st.session_state["ex9_component_state"] = state
        st.session_state["ex9_correct"] = bool(state.get("complete") or state.get("success"))
        st.session_state["ex9_errors"] = int(state.get("errors", 0) or 0)

    c_reset, _ = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex9",
            use_container_width=True,
        ):
            _ex9_restart()
            st.rerun()

    if st.session_state.get("ex9_correct", False):
        ex9_state = st.session_state.get("ex9_component_state") or {}
        correct_count = int(ex9_state.get("correct_count", 0) or 0)
        total_count = int(ex9_state.get("total", len(EXERCISE9_ITEMS)) or len(EXERCISE9_ITEMS))
        error_count = int(ex9_state.get("errors", 0) or 0)

        if correct_count == total_count:
            st.success(f"🎉 Bravo ! {correct_count} / {total_count} bonnes réponses, sans erreur.")
        else:
            st.warning(
                f"📊 Exercice terminé : {correct_count} / {total_count} bonnes réponses "
                f"et {error_count} erreur(s)."
            )

        st.info(
            "🔎 À retenir : **CO** contient les symboles C et O : c’est une molécule. "
            "**Co** est le symbole du cobalt : il représente ici un atome de cobalt."
        )

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex9_result_saved", False)
        ):
            ex9_state_final = st.session_state.get("ex9_component_state") or {}
            correct_count = int(ex9_state_final.get("correct_count", 0) or 0)
            total_count = int(
                ex9_state_final.get("total", len(EXERCISE9_ITEMS))
                or len(EXERCISE9_ITEMS)
            )
            total_errors = int(ex9_state_final.get("errors", 0) or 0)
            score = round(100 * correct_count / max(1, total_count))

            record_training_result(
                student,
                "exercise9_atom_or_molecule",
                score,
                correct_count,
                total_count,
                errors=total_errors,
            )
            st.session_state["ex9_result_saved"] = True




# ============================================================
# EXERCICE 10 — ÉTHANOL
# ============================================================

EXERCISE10_IMAGE_CANDIDATES = [
    Path("assets/chapitre_1/exercice 10/Ethanol.png"),
    Path("assets/chapitre_1/exercice_10/Ethanol.png"),
    Path("assets/chapitre_1/exercice 10/ethanol.png"),
    Path("assets/chapitre_1/exercice_10/ethanol.png"),
]


def _ex10_find_image():
    for candidate in EXERCISE10_IMAGE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _chem_formula_norm(value):
    value = str(value or "").strip()
    sub_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    value = value.translate(sub_map)
    value = value.replace(" ", "").replace("·", "")
    return value


def _ex10_int(value):
    """
    Extrait le premier nombre entier saisi par l'élève.

    Exemples :
    - "2" -> 2
    - "2 noir" -> 2
    - "6 blancs" -> 6
    - "1 rouge" -> 1
    """
    raw = str(value or "").strip()
    if not raw:
        return None

    match = re.search(r"-?\d+", raw)
    if not match:
        return None

    try:
        return int(match.group(0))
    except Exception:
        return None


def _ex10_validate_q1():
    generation = int(st.session_state.get("ex10_generation", 0))
    c = _ex10_int(st.session_state.get(f"ex10_q1_c_{generation}", ""))
    h = _ex10_int(st.session_state.get(f"ex10_q1_h_{generation}", ""))
    o = _ex10_int(st.session_state.get(f"ex10_q1_o_{generation}", ""))

    if c is None or h is None or o is None:
        st.session_state["ex10_q1_feedback"] = "empty"
        st.session_state["ex10_q1_wrong_fields"] = []
        return

    expected = {
        "carbone": 2,
        "hydrogène": 6,
        "oxygène": 1,
    }
    given = {
        "carbone": c,
        "hydrogène": h,
        "oxygène": o,
    }

    wrong_fields = [
        label
        for label, expected_value in expected.items()
        if given[label] != expected_value
    ]
    st.session_state["ex10_q1_wrong_fields"] = wrong_fields

    if not wrong_fields:
        st.session_state["ex10_q1_correct"] = True
        st.session_state["ex10_q1_feedback"] = "correct"
    else:
        st.session_state["ex10_q1_correct"] = False
        st.session_state["ex10_q1_errors"] = int(
            st.session_state.get("ex10_q1_errors", 0)
        ) + 1
        st.session_state["ex10_q1_feedback"] = "wrong"


def _ex10_validate_q2():
    generation = int(st.session_state.get("ex10_generation", 0))
    value = _chem_formula_norm(
        st.session_state.get(f"ex10_q2_{generation}", "")
    )

    if not value:
        st.session_state["ex10_q2_feedback"] = "empty"
        return

    if value in {"C2H6O", "C2H5OH"}:
        st.session_state["ex10_q2_correct"] = True
        st.session_state["ex10_q2_feedback"] = "correct"
    else:
        st.session_state["ex10_q2_correct"] = False
        st.session_state["ex10_q2_errors"] = int(
            st.session_state.get("ex10_q2_errors", 0)
        ) + 1
        st.session_state["ex10_q2_feedback"] = "wrong"


def _ex10_feedback(question):
    feedback = st.session_state.get(f"ex10_q{question}_feedback")
    errors = int(st.session_state.get(f"ex10_q{question}_errors", 0))

    if feedback == "correct":
        if question == 1:
            st.success(
                "✅ Bonne composition : 2 atomes de carbone, "
                "6 atomes d’hydrogène et 1 atome d’oxygène."
            )
        else:
            st.success("✅ Bonne formule : C₂H₆O.")
        return

    if feedback == "empty":
        st.warning("✏️ Complète la réponse avant de valider.")
        return

    if feedback != "wrong":
        return

    if question == 1:
        wrong_fields = st.session_state.get("ex10_q1_wrong_fields", [])

        if wrong_fields:
            if len(wrong_fields) == 1:
                detail = f"Recompte les atomes d’{wrong_fields[0]}."
            else:
                detail = (
                    "Recompte les atomes de "
                    + ", ".join(wrong_fields[:-1])
                    + " et d’"
                    + wrong_fields[-1]
                    + "."
                )
        else:
            detail = "Recompte séparément chaque sorte d’atome."

        if errors == 1:
            st.warning(f"💡 {detail}")
        else:
            st.warning(
                f"🔎 {detail} Utilise la légende : "
                "noir = carbone, blanc = hydrogène, rouge = oxygène."
            )
    else:
        if errors == 1:
            st.warning(
                "💡 Ta formule doit traduire le nombre d’atomes de chaque élément "
                "que tu viens de compter."
            )
        else:
            st.warning(
                "🔎 Repars de ta composition : C, H et O doivent apparaître avec "
                "les bons indices."
            )


def _ex10_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex10_generation", 0))
    touched = any(
        str(st.session_state.get(key, "")).strip()
        for key in [
            f"ex10_q1_c_{generation}",
            f"ex10_q1_h_{generation}",
            f"ex10_q1_o_{generation}",
            f"ex10_q2_{generation}",
        ]
    )
    if not touched:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise10_ethanol"
        and r.get("activity_kind") == "training"
    ]

    total_errors = int(st.session_state.get("ex10_q1_errors", 0)) + int(
        st.session_state.get("ex10_q2_errors", 0)
    )

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise10_ethanol",
        "resource_label": PILOT_CONTENTS["exercise10_ethanol"]["label"],
        "chapter": PILOT_CONTENTS["exercise10_ethanol"]["chapter"],
        "score_percent": None,
        "completed_items": 0,
        "total_items": 2,
        "errors": total_errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise10():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex10_"):
            st.session_state.pop(key, None)


def _ex10_restart():
    _ex10_record_restart_if_needed()
    generation = int(st.session_state.get("ex10_generation", 0))
    reset_exercise10()
    st.session_state["ex10_generation"] = generation + 1


def page_exercise10_ethanol():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise10_ethanol"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex10-box{
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
            padding:1rem 1.1rem;margin:.7rem 0 1rem;font-size:1.08rem;
            line-height:1.55;color:#314b69;
        }
        .chem-legend{
            display:flex;gap:18px;flex-wrap:wrap;align-items:center;
            padding:.65rem .8rem;border:1px solid #dbe5ef;border-radius:12px;
            background:#fff;margin:.5rem 0 1rem;
        }
        .chem-dot{
            display:inline-block;width:18px;height:18px;border-radius:50%;
            vertical-align:middle;margin-right:6px;border:1px solid #718096;
        }
        div[data-testid="stTextInput"] input{
            font-size:1.12rem!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Éthanol</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🧪 Exercice 10 — Éthanol</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="ex10-box"><strong>Objectif :</strong> lire un modèle moléculaire, '
        'déterminer la composition d’une molécule et écrire sa formule.</div>',
        unsafe_allow_html=True,
    )

    image_path = _ex10_find_image()
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        st.markdown("### Modèle moléculaire de l’éthanol")
        if image_path is not None:
            st.image(str(image_path), width=430)
        else:
            st.warning(
                "Image manquante : ajoute « Ethanol.png » dans "
                "assets/chapitre_1/exercice 10/."
            )

    with right:
        st.markdown(
            """
            <div class="chem-legend">
              <span><span class="chem-dot" style="background:#15191f"></span><strong>Carbone</strong></span>
              <span><span class="chem-dot" style="background:#ffffff"></span><strong>Hydrogène</strong></span>
              <span><span class="chem-dot" style="background:#e53935"></span><strong>Oxygène</strong></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "Observe attentivement le modèle et compte chaque sorte d’atome."
        )

    generation = int(st.session_state.get("ex10_generation", 0))

    st.markdown("### 1. Indique la composition de la molécule d’éthanol.")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        st.text_input(
            "Nombre d’atomes de carbone",
            key=f"ex10_q1_c_{generation}",
            disabled=bool(st.session_state.get("ex10_q1_correct", False)),
        )
    with c2:
        st.text_input(
            "Nombre d’atomes d’hydrogène",
            key=f"ex10_q1_h_{generation}",
            disabled=bool(st.session_state.get("ex10_q1_correct", False)),
        )
    with c3:
        st.text_input(
            "Nombre d’atomes d’oxygène",
            key=f"ex10_q1_o_{generation}",
            disabled=bool(st.session_state.get("ex10_q1_correct", False)),
        )

    st.button(
        "Valider la composition",
        key="ex10_validate_q1",
        use_container_width=True,
        type="primary",
        on_click=_ex10_validate_q1,
        disabled=bool(st.session_state.get("ex10_q1_correct", False)),
    )
    _ex10_feedback(1)

    st.markdown("### 2. Écris la formule de la molécule d’éthanol.")
    st.text_input(
        "Formule",
        key=f"ex10_q2_{generation}",
        placeholder="Écris la formule ici",
        disabled=bool(st.session_state.get("ex10_q2_correct", False)),
    )
    st.button(
        "Valider la formule",
        key="ex10_validate_q2",
        use_container_width=True,
        on_click=_ex10_validate_q2,
        disabled=bool(st.session_state.get("ex10_q2_correct", False)),
    )
    _ex10_feedback(2)

    completed = sum(
        int(bool(st.session_state.get(f"ex10_q{i}_correct", False)))
        for i in (1, 2)
    )

    st.markdown("### Ton avancement")
    st.progress(completed / 2)
    st.write(f"**{completed} / 2 parties réussies**")

    c_reset, _ = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex10",
            use_container_width=True,
        ):
            _ex10_restart()
            st.rerun()

    if completed == 2:
        st.success(
            "🎉 Exercice terminé : tu sais passer du modèle moléculaire "
            "à la composition puis à la formule."
        )

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex10_result_saved", False)
        ):
            errors = int(st.session_state.get("ex10_q1_errors", 0)) + int(
                st.session_state.get("ex10_q2_errors", 0)
            )
            score = round(100 * 2 / max(2, 2 + errors))
            record_training_result(
                student,
                "exercise10_ethanol",
                score,
                2,
                2,
                errors=errors,
            )
            st.session_state["ex10_result_saved"] = True


# ============================================================
# EXERCICE 11 — PROTOXYDE D'AZOTE
# ============================================================

def _ex11_norm_text(value):
    return _ex8_norm(value)


def _ex11_validate_simple(question, validator):
    generation = int(st.session_state.get("ex11_generation", 0))
    value = st.session_state.get(f"ex11_q{question}_{generation}", "")

    if not str(value).strip():
        st.session_state[f"ex11_q{question}_feedback"] = "empty"
        return

    if validator(value):
        st.session_state[f"ex11_q{question}_correct"] = True
        st.session_state[f"ex11_q{question}_feedback"] = "correct"
    else:
        st.session_state[f"ex11_q{question}_correct"] = False
        st.session_state[f"ex11_q{question}_errors"] = int(
            st.session_state.get(f"ex11_q{question}_errors", 0)
        ) + 1
        st.session_state[f"ex11_q{question}_feedback"] = "wrong"


def _ex11_validate_q1():
    _ex11_validate_simple(
        1,
        lambda v: str(v or "").strip() == "N",
    )


def _ex11_validate_q2():
    _ex11_validate_simple(
        2,
        lambda v: _chem_formula_norm(v) == "N2",
    )


def _ex11_validate_q4():
    def ok(value):
        v = _ex11_norm_text(value)
        return (
            "air" in v
            or "atmosphere" in v
            or "atmospherique" in v
        )
    _ex11_validate_simple(4, ok)


def _ex11_validate_q6():
    _ex11_validate_simple(
        6,
        lambda v: _chem_formula_norm(v) == "N2O",
    )


def _ex11_feedback(question):
    feedback = st.session_state.get(f"ex11_q{question}_feedback")
    errors = int(st.session_state.get(f"ex11_q{question}_errors", 0))

    if feedback == "correct":
        messages = {
            1: "✅ Le symbole de l’azote est N.",
            2: "✅ La formule du diazote est N₂.",
            4: "✅ Oui. Le diazote est présent en grande quantité dans l’air.",
            6: "✅ Le modèle contient 2 atomes d’azote et 1 atome d’oxygène : N₂O.",
        }
        st.success(messages.get(question, "✅ Bonne réponse."))
        return

    if feedback == "empty":
        st.warning("✏️ Rédige une réponse avant de valider.")
        return

    if feedback != "wrong":
        return

    if question == 1:
        st.warning(
            "💡 Consulte le tableau périodique et retrouve l’élément « azote »."
        )
    elif question == 2:
        if errors == 1:
            st.warning("💡 Le préfixe « di- » donne une indication sur le nombre d’atomes.")
        else:
            st.warning("🔎 Pars du symbole N et indique qu’il y a deux atomes.")
    elif question == 4:
        if errors == 1:
            st.warning("💡 Pense au mélange gazeux que nous respirons.")
        else:
            st.warning("🔎 Le diazote est le principal constituant de l’air.")
    elif question == 6:
        if errors == 1:
            st.warning("💡 Compte les boules bleues et rouges du modèle.")
        else:
            st.warning("🔎 Bleu = azote (N) ; rouge = oxygène (O).")


# ---------- Q3 : choix Atome / Molécule, premier choix définitif ----------

EX11_Q3_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:#17345f;background:#fff}
.wrap{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:2px 0 6px}
button{
  min-height:58px;border-radius:12px;border:1px solid #cbd8e8;background:#fff;
  color:#17345f;font-size:16px;font-weight:850;cursor:pointer;transition:.15s ease
}
button:hover:not(:disabled){background:#eef6ff;border-color:#7caee2}
button.correct{background:#e9f8ee;border-color:#62bb7a;color:#24623a}
button.wrong{background:#fff0f0;border-color:#e37272;color:#a93232}
button:disabled{cursor:default}
</style>
</head>
<body>
<div class="wrap">
  <button id="atom">Atome</button>
  <button id="molecule">Molécule</button>
</div>
<script>
(function(){
  let initialized=false;
  let generation=0;
  let storageId="prototype";
  let state={complete:false,correct_first_try:false,selected:"",errors:0};

  function ready(){
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:componentReady",apiVersion:1},"*");
  }
  function setHeight(){
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:setFrameHeight",height:72},"*");
  }
  function key(){return "ludo_ex11_q3_v1_"+storageId+"_"+String(generation)}
  function load(){
    try{
      const p=JSON.parse(sessionStorage.getItem(key())||"null");
      return p||{complete:false,correct_first_try:false,selected:"",errors:0};
    }catch(e){return{complete:false,correct_first_try:false,selected:"",errors:0}}
  }
  function save(){try{sessionStorage.setItem(key(),JSON.stringify(state))}catch(e){}}
  function send(){
    window.parent.postMessage({
      isStreamlitMessage:true,type:"streamlit:setComponentValue",
      value:state
    },"*");
  }
  function render(){
    const a=document.getElementById("atom");
    const m=document.getElementById("molecule");
    a.className="";m.className="";
    if(state.complete){
      m.classList.add("correct");
      if(state.selected==="Atome")a.classList.add("wrong");
      a.disabled=true;m.disabled=true;
    }
    setHeight();
  }
  function choose(label){
    if(state.complete)return;
    state.complete=true;
    state.selected=label;
    state.correct_first_try=(label==="Molécule");
    if(!state.correct_first_try)state.errors=1;
    save();render();send();
  }
  document.getElementById("atom").onclick=()=>choose("Atome");
  document.getElementById("molecule").onclick=()=>choose("Molécule");

  window.addEventListener("message",(event)=>{
    const d=event.data||{};
    if(d.type!=="streamlit:render")return;
    const args=d.args||{};
    const ng=Number(args.generation||0);
    const ns=String(args.storage_id||"prototype");
    const changed=!initialized||ng!==generation||ns!==storageId;
    generation=ng;storageId=ns;
    if(changed){state=load();render();initialized=true}else setHeight();
  });
  ready();
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex11_q3_component():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex11_q3_component_v1"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(EX11_Q3_HTML, encoding="utf-8")
    return components.declare_component(
        "ex11_dinitrogen_atom_molecule_v1",
        path=str(component_dir),
    )


def render_ex11_q3(generation):
    component = _ex11_q3_component()
    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )
    return component(
        generation=int(generation),
        storage_id=storage_id,
        key=f"ex11_q3_v1_{generation}",
        default={
            "complete": False,
            "correct_first_try": False,
            "selected": "",
            "errors": 0,
        },
    )


# ---------- Q5 : constructeur moléculaire ----------

EX11_BUILDER_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,Arial,sans-serif;color:#17345f;background:#fff}
.wrap{width:100%;padding:2px 0 8px}
.info{
  padding:10px 12px;border:1px solid #cfe0fb;border-radius:12px;background:#f5f9ff;
  font-size:13px;line-height:1.45;color:#4c6481;margin-bottom:10px
}
.palette{
  display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:center;
  padding:12px;border:1px solid #dbe5ef;border-radius:14px;background:#f8fafc
}
.tool{
  width:54px;height:54px;border-radius:50%;border:3px solid rgba(0,0,0,.22);
  display:flex;align-items:center;justify-content:center;font-weight:900;font-size:16px;
  user-select:none;touch-action:none;cursor:grab;box-shadow:0 3px 8px rgba(0,0,0,.12)
}
.tool.h{background:#fff;color:#425466}
.tool.c{background:#15191f;color:#fff}
.tool.n{background:#2c8be6;color:#fff}
.tool.o{background:#e53935;color:#fff}
.tool.cl{background:#37a85b;color:#fff}
.tool.bond{
  width:78px;height:32px;border-radius:9px;background:#e9eef4;color:#34495e;
  border:2px solid #9aa8b7;font-size:22px
}
.model-shell{
  margin-top:12px;padding:14px;border:1px solid #cfdbe8;border-radius:15px;background:#fff
}
.model-title{text-align:center;font-weight:850;margin-bottom:10px}
.track-wrap{overflow-x:auto;padding:5px 0}
.track{
  min-width:510px;display:flex;align-items:center;justify-content:center;gap:6px
}
.atom-slot{
  width:64px;height:64px;border:2px dashed #aebfd2;border-radius:50%;background:#f9fbfd;
  display:flex;align-items:center;justify-content:center;flex:0 0 auto;
  color:#7a8da4;font-size:12px;cursor:pointer
}
.atom-slot.filled{
  border-style:solid;font-weight:900;font-size:17px;color:#fff;
  box-shadow:0 3px 8px rgba(0,0,0,.12)
}
.atom-slot.H{background:#fff;color:#425466;border-color:#9aa8b7}
.atom-slot.C{background:#15191f;border-color:#15191f}
.atom-slot.N{background:#2c8be6;border-color:#1e6db5}
.atom-slot.O{background:#e53935;border-color:#b62825}
.atom-slot.Cl{background:#37a85b;border-color:#247840}
.bond-slot{
  width:48px;height:18px;border:2px dashed #b2c0cf;border-radius:7px;background:#f9fbfd;
  display:flex;align-items:center;justify-content:center;flex:0 0 auto;cursor:pointer
}
.bond-slot.filled{
  border-style:solid;background:#8392a3;border-color:#657383
}
.bond-slot.filled::after{
  content:"";display:block;width:36px;height:6px;border-radius:4px;background:#34495e
}
.formula-row{
  display:grid;grid-template-columns:1fr 180px;gap:10px;margin-top:12px;align-items:end
}
.formula-row label{display:block;font-size:13px;font-weight:800;margin-bottom:5px}
.formula-row input{
  width:100%;height:48px;border:2px solid #8fbceb;border-radius:11px;background:#edf6ff;
  padding:0 12px;font-size:17px;font-weight:750;color:#17345f;outline:none
}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.action{
  min-height:48px;border-radius:11px;border:1px solid #a9c8eb;background:#fff;color:#175aa8;
  font-weight:850;padding:0 14px;cursor:pointer
}
.action.primary{background:#2878d4;border-color:#2878d4;color:#fff}
.feedback{
  margin-top:10px;padding:10px 12px;border-radius:11px;border:1px solid #dfe6ef;
  background:#f7f9fc;color:#61738b;font-size:13px;font-weight:750;min-height:42px
}
.feedback.ok{background:#eaf8ef;border-color:#b8e2c4;color:#24623a}
.feedback.bad{background:#fff5df;border-color:#f0cf84;color:#8a5a00}
.ghost{
  position:fixed;z-index:99999;pointer-events:none;opacity:.92;transform:translate(-50%,-50%);
}
@media(max-width:700px){
  .track{min-width:350px;gap:3px}
  .atom-slot{width:46px;height:46px}
  .bond-slot{width:25px;height:14px}
  .bond-slot.filled::after{width:20px;height:5px}
  .formula-row{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="info">
    Fais glisser des <strong>atomes</strong> et des <strong>barres de liaison</strong>
    dans la zone de construction. Plusieurs éléments sont proposés : à toi de choisir.
    Clique sur un élément déjà placé pour le retirer.
  </div>

  <div class="palette">
    <div class="tool h" data-kind="atom" data-value="H">H</div>
    <div class="tool c" data-kind="atom" data-value="C">C</div>
    <div class="tool n" data-kind="atom" data-value="N">N</div>
    <div class="tool o" data-kind="atom" data-value="O">O</div>
    <div class="tool cl" data-kind="atom" data-value="Cl">Cl</div>
    <div class="tool bond" data-kind="bond" data-value="bond">—</div>
  </div>

  <div class="model-shell">
    <div class="model-title">Ton modèle du dioxyde d’azote</div>
    <div class="track-wrap">
      <div class="track">
        <div class="atom-slot" data-slot="0"></div>
        <div class="bond-slot" data-bond="0"></div>
        <div class="atom-slot" data-slot="1"></div>
        <div class="bond-slot" data-bond="1"></div>
        <div class="atom-slot" data-slot="2"></div>
        <div class="bond-slot" data-bond="2"></div>
        <div class="atom-slot" data-slot="3"></div>
        <div class="bond-slot" data-bond="3"></div>
        <div class="atom-slot" data-slot="4"></div>
      </div>
    </div>

    <div class="formula-row">
      <div>
        <label for="formula">Formule du dioxyde d’azote</label>
        <input id="formula" type="text" placeholder="Écris la formule" autocomplete="off">
      </div>
      <div class="actions">
        <button class="action" id="clearBtn" type="button">↻ Effacer</button>
        <button class="action primary" id="checkBtn" type="button">Vérifier</button>
      </div>
    </div>
    <div class="feedback" id="feedback">Construis ton modèle puis vérifie ta réponse.</div>
  </div>
</div>

<script>
(function(){
  let initialized=false;
  let generation=0;
  let storageId="prototype";
  let state={slots:["","","","",""],bonds:[false,false,false,false],formula:"",errors:0,success:false};
  let drag=null;

  function ready(){
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:componentReady",apiVersion:1},"*");
  }
  function setHeight(){
    const wrap=document.querySelector(".wrap");
    const h=wrap?Math.ceil(wrap.getBoundingClientRect().height)+12:520;
    window.parent.postMessage({isStreamlitMessage:true,type:"streamlit:setFrameHeight",height:h},"*");
  }
  function key(){return "ludo_ex11_builder_v1_"+storageId+"_"+String(generation)}
  function fresh(){
    return{slots:["","","","",""],bonds:[false,false,false,false],formula:"",errors:0,success:false};
  }
  function load(){
    try{
      const p=JSON.parse(sessionStorage.getItem(key())||"null");
      if(!p)return fresh();
      return{
        slots:Array.from({length:5},(_,i)=>String(p.slots?.[i]||"")),
        bonds:Array.from({length:4},(_,i)=>Boolean(p.bonds?.[i])),
        formula:String(p.formula||""),
        errors:Number(p.errors||0),
        success:Boolean(p.success)
      };
    }catch(e){return fresh()}
  }
  function save(){try{sessionStorage.setItem(key(),JSON.stringify(state))}catch(e){}}
  function send(){
    window.parent.postMessage({
      isStreamlitMessage:true,type:"streamlit:setComponentValue",
      value:{success:state.success,errors:state.errors,slots:state.slots,bonds:state.bonds,formula:state.formula}
    },"*");
  }
  function normFormula(v){
    const map={"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","₅":"5","₆":"6","₇":"7","₈":"8","₉":"9"};
    return String(v||"").trim().split("").map(ch=>map[ch]||ch).join("").replace(/\s+/g,"");
  }
  function render(){
    document.querySelectorAll(".atom-slot").forEach(el=>{
      const i=Number(el.dataset.slot);
      const sym=state.slots[i]||"";
      el.className="atom-slot"+(sym?" filled "+sym:"");
      el.textContent=sym;
    });
    document.querySelectorAll(".bond-slot").forEach(el=>{
      const i=Number(el.dataset.bond);
      el.className="bond-slot"+(state.bonds[i]?" filled":"");
    });
    const input=document.getElementById("formula");
    input.value=state.formula;
    input.disabled=state.success;
    document.getElementById("checkBtn").disabled=state.success;
    document.querySelectorAll(".tool").forEach(t=>t.style.pointerEvents=state.success?"none":"auto");
    setTimeout(setHeight,20);
  }

  function consecutiveONO(){
    const occupied=state.slots.map((s,i)=>s?i:-1).filter(i=>i>=0);
    if(occupied.length!==3)return {ok:false,composition:false};

    const syms=occupied.map(i=>state.slots[i]);
    const counts={
      O:syms.filter(x=>x==="O").length,
      N:syms.filter(x=>x==="N").length
    };
    const composition=counts.O===2&&counts.N===1&&syms.every(x=>x==="O"||x==="N");

    if(!composition)return {ok:false,composition:false};

    const consecutive=occupied[1]===occupied[0]+1&&occupied[2]===occupied[1]+1;
    if(!consecutive)return {ok:false,composition:true};

    const ordered=
      state.slots[occupied[0]]==="O"&&
      state.slots[occupied[1]]==="N"&&
      state.slots[occupied[2]]==="O";

    if(!ordered)return {ok:false,composition:true};

    const neededBond1=occupied[0];
    const neededBond2=occupied[1];
    const bondsOk=state.bonds[neededBond1]&&state.bonds[neededBond2];

    const extraBond=state.bonds.some((v,i)=>v&&i!==neededBond1&&i!==neededBond2);

    return {ok:bondsOk&&!extraBond,composition:true,ordered:true,bondsOk:bondsOk&&!extraBond};
  }

  function check(){
    if(state.success)return;
    state.formula=document.getElementById("formula").value;
    const model=consecutiveONO();
    const formulaOk=normFormula(state.formula)==="NO2";
    const fb=document.getElementById("feedback");

    if(model.ok&&formulaOk){
      state.success=true;
      fb.className="feedback ok";
      fb.textContent="✅ Modèle et formule cohérents.";
    }else{
      state.errors+=1;
      fb.className="feedback bad";

      if(model.composition && !model.ok){
        fb.textContent="💡 Tu as choisi les bons types et nombres d’atomes, mais leur organisation ou les liaisons ne correspondent pas encore au modèle attendu.";
      }else if(model.ok && !formulaOk){
        fb.textContent="💡 Ton modèle convient. Vérifie maintenant la formule que tu as écrite.";
      }else if(state.errors===1){
        fb.textContent="💡 Observe le nom « dioxyde d’azote » : il donne des informations sur les éléments présents et leur nombre.";
      }else{
        fb.textContent="🔎 Le préfixe « di- » donne une indication importante sur le nombre d’atomes d’oxygène.";
      }
    }

    save();render();send();
  }

  function clearAll(){
    if(state.success)return;
    state.slots=["","","","",""];
    state.bonds=[false,false,false,false];
    state.formula="";
    document.getElementById("feedback").className="feedback";
    document.getElementById("feedback").textContent="Construis ton modèle puis vérifie ta réponse.";
    save();render();send();
  }

  function ghostFor(tool){
    const g=tool.cloneNode(true);
    g.classList.add("ghost");
    const r=tool.getBoundingClientRect();
    g.style.width=r.width+"px";g.style.height=r.height+"px";
    document.body.appendChild(g);
    return g;
  }

  function nearest(selector,x,y,maxD){
    let best=null,bestD=Infinity;
    document.querySelectorAll(selector).forEach(el=>{
      const r=el.getBoundingClientRect();
      const cx=r.left+r.width/2,cy=r.top+r.height/2;
      const d=Math.hypot(x-cx,y-cy);
      if(d<bestD){bestD=d;best=el}
    });
    return bestD<=maxD?best:null;
  }

  function startDrag(e,tool){
    if(state.success)return;
    e.preventDefault();
    const ghost=ghostFor(tool);
    drag={
      pointerId:e.pointerId,
      kind:tool.dataset.kind,
      value:tool.dataset.value,
      ghost
    };
    ghost.style.left=e.clientX+"px";
    ghost.style.top=e.clientY+"px";
    tool.setPointerCapture?.(e.pointerId);
  }

  function moveDrag(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    drag.ghost.style.left=e.clientX+"px";
    drag.ghost.style.top=e.clientY+"px";
  }

  function endDrag(e){
    if(!drag||e.pointerId!==drag.pointerId)return;
    e.preventDefault();

    if(drag.kind==="atom"){
      const target=nearest(".atom-slot",e.clientX,e.clientY,60);
      if(target){
        const i=Number(target.dataset.slot);
        state.slots[i]=drag.value;
      }
    }else{
      const target=nearest(".bond-slot",e.clientX,e.clientY,55);
      if(target){
        const i=Number(target.dataset.bond);
        state.bonds[i]=true;
      }
    }

    drag.ghost.remove();
    drag=null;
    save();render();send();
  }

  document.querySelectorAll(".tool").forEach(tool=>{
    tool.addEventListener("pointerdown",e=>startDrag(e,tool));
  });
  document.addEventListener("pointermove",moveDrag);
  document.addEventListener("pointerup",endDrag);
  document.addEventListener("pointercancel",endDrag);

  document.querySelectorAll(".atom-slot").forEach(el=>{
    el.addEventListener("click",()=>{
      if(state.success)return;
      state.slots[Number(el.dataset.slot)]="";
      save();render();send();
    });
  });
  document.querySelectorAll(".bond-slot").forEach(el=>{
    el.addEventListener("click",()=>{
      if(state.success)return;
      state.bonds[Number(el.dataset.bond)]=false;
      save();render();send();
    });
  });

  document.getElementById("formula").addEventListener("input",e=>{
    if(state.success)return;
    state.formula=e.target.value;
    save();send();
  });
  document.getElementById("checkBtn").onclick=check;
  document.getElementById("clearBtn").onclick=clearAll;

  window.addEventListener("message",(event)=>{
    const d=event.data||{};
    if(d.type!=="streamlit:render")return;
    const args=d.args||{};
    const ng=Number(args.generation||0);
    const ns=String(args.storage_id||"prototype");
    const changed=!initialized||ng!==generation||ns!==storageId;
    generation=ng;storageId=ns;
    if(changed){
      state=load();
      render();
      initialized=true;
    }else setHeight();
  });

  ready();
})();
</script>
</body>
</html>
"""


@st.cache_resource
def _ex11_builder_component():
    component_dir = Path(tempfile.gettempdir()) / "ludo_ex11_builder_component_v1"
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "index.html").write_text(
        EX11_BUILDER_HTML,
        encoding="utf-8",
    )
    return components.declare_component(
        "ex11_no2_builder_v1",
        path=str(component_dir),
    )


def render_ex11_builder(generation):
    component = _ex11_builder_component()
    student = st.session_state.get("app_student") or {}
    storage_id = str(
        student.get("id")
        or st.session_state.get("teacher_id")
        or "prototype"
    )
    return component(
        generation=int(generation),
        storage_id=storage_id,
        key=f"ex11_builder_v1_{generation}",
        default={
            "success": False,
            "errors": 0,
            "slots": [],
            "bonds": [],
            "formula": "",
        },
    )


def _ex11_record_restart_if_needed():
    student = st.session_state.get("app_student")
    if st.session_state.get("app_user_type") != "student" or not student:
        return

    generation = int(st.session_state.get("ex11_generation", 0))
    q3_state = st.session_state.get("ex11_q3_component_state") or {}
    q5_state = st.session_state.get("ex11_q5_component_state") or {}

    touched = bool(
        any(
            str(st.session_state.get(f"ex11_q{i}_{generation}", "")).strip()
            for i in (1, 2, 4, 6)
        )
        or q3_state.get("complete")
        or q5_state.get("errors")
        or any(q5_state.get("slots") or [])
        or str(q5_state.get("formula", "")).strip()
    )
    if not touched:
        return

    teacher_id = student.get("_teacher_id")
    if not teacher_id:
        return

    rows = get_activity_log(teacher_id)
    previous = [
        r for r in rows
        if r.get("student_id") == student.get("id")
        and r.get("resource_id") == "exercise11_nitrous_oxide"
        and r.get("activity_kind") == "training"
    ]

    errors = sum(
        int(st.session_state.get(f"ex11_q{i}_errors", 0))
        for i in (1, 2, 4, 6)
    )
    errors += int(q3_state.get("errors", 0) or 0)
    errors += int(q5_state.get("errors", 0) or 0)

    rows.append({
        "id": secrets.token_urlsafe(10),
        "activity_kind": "training",
        "status": "restarted",
        "student_id": student.get("id"),
        "first_name": student.get("first_name"),
        "last_initial": student.get("last_initial"),
        "class_name": student.get("class_name"),
        "resource_id": "exercise11_nitrous_oxide",
        "resource_label": PILOT_CONTENTS["exercise11_nitrous_oxide"]["label"],
        "chapter": PILOT_CONTENTS["exercise11_nitrous_oxide"]["chapter"],
        "score_percent": None,
        "completed_items": 0,
        "total_items": 6,
        "errors": errors,
        "attempt_number": len(previous) + 1,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_activity_log(rows, teacher_id)


def reset_exercise11():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex11_"):
            st.session_state.pop(key, None)


def _ex11_restart():
    _ex11_record_restart_if_needed()
    generation = int(st.session_state.get("ex11_generation", 0))
    reset_exercise11()
    st.session_state["ex11_generation"] = generation + 1


def _ex11_n2o_model_html():
    return """
    <div style="
      display:flex;justify-content:center;align-items:center;
      padding:1.1rem;margin:.6rem 0 1rem;border:1px solid #dbe5ef;
      border-radius:14px;background:#f8fafc;">
      <div style="width:72px;height:72px;border-radius:50%;background:#2c8be6;
                  border:3px solid #1e6db5;box-shadow:0 4px 10px rgba(0,0,0,.12)"></div>
      <div style="width:34px;height:8px;background:#657383;border-radius:5px"></div>
      <div style="width:72px;height:72px;border-radius:50%;background:#2c8be6;
                  border:3px solid #1e6db5;box-shadow:0 4px 10px rgba(0,0,0,.12)"></div>
      <div style="width:34px;height:8px;background:#657383;border-radius:5px"></div>
      <div style="width:72px;height:72px;border-radius:50%;background:#e53935;
                  border:3px solid #b62825;box-shadow:0 4px 10px rgba(0,0,0,.12)"></div>
    </div>
    """


def page_exercise11_nitrous_oxide():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise11_nitrous_oxide"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        .ex11-context{
            background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
            padding:1rem 1.1rem;margin:.7rem 0 1rem;font-size:1.08rem;
            line-height:1.55;color:#314b69;
        }
        .ex11-rule{
            display:flex;gap:16px;flex-wrap:wrap;align-items:center;
            padding:.65rem .8rem;border:1px solid #dbe5ef;border-radius:12px;
            background:#fff;margin:.5rem 0 1rem;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea{
            font-size:1.12rem!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Protoxyde d’azote</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">💨 Exercice 11 — Protoxyde d’azote</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="ex11-context">
          Le <strong>protoxyde d’azote</strong>, parfois appelé « gaz hilarant »,
          est un gaz incolore utilisé notamment dans certains usages médicaux et
          techniques. C’est également un gaz à effet de serre. Il contient de
          l’<strong>azote</strong>.
        </div>
        """,
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex11_generation", 0))

    # Q1
    st.markdown("### 1. Donne le symbole chimique de l’azote.")
    st.text_input(
        "Symbole de l’azote",
        key=f"ex11_q1_{generation}",
        placeholder="Symbole",
        disabled=bool(st.session_state.get("ex11_q1_correct", False)),
    )
    st.button(
        "Valider la question 1",
        key="ex11_validate_q1",
        use_container_width=True,
        on_click=_ex11_validate_q1,
        disabled=bool(st.session_state.get("ex11_q1_correct", False)),
    )
    _ex11_feedback(1)

    # Q2
    st.markdown("### 2. Donne la formule du diazote.")
    st.text_input(
        "Formule du diazote",
        key=f"ex11_q2_{generation}",
        placeholder="Formule",
        disabled=bool(st.session_state.get("ex11_q2_correct", False)),
    )
    st.button(
        "Valider la question 2",
        key="ex11_validate_q2",
        use_container_width=True,
        on_click=_ex11_validate_q2,
        disabled=bool(st.session_state.get("ex11_q2_correct", False)),
    )
    _ex11_feedback(2)

    # Q3
    st.markdown("### 3. Le diazote est-il un atome ou une molécule ?")
    q3_state = render_ex11_q3(generation)
    if isinstance(q3_state, dict):
        st.session_state["ex11_q3_component_state"] = q3_state
        st.session_state["ex11_q3_correct"] = bool(q3_state.get("complete"))

        if q3_state.get("complete"):
            if q3_state.get("correct_first_try"):
                st.success("✅ Bonne réponse : le diazote est une molécule.")
            else:
                st.warning(
                    "❌ Ton premier choix était faux. Le diazote est une molécule : "
                    "il est constitué de deux atomes d’azote."
                )

    # Q4
    st.markdown("### 4. Où peut-on trouver du diazote ?")
    st.text_area(
        "Ta réponse",
        key=f"ex11_q4_{generation}",
        height=90,
        placeholder="Indique où le diazote est présent.",
        disabled=bool(st.session_state.get("ex11_q4_correct", False)),
    )
    st.button(
        "Valider la question 4",
        key="ex11_validate_q4",
        use_container_width=True,
        on_click=_ex11_validate_q4,
        disabled=bool(st.session_state.get("ex11_q4_correct", False)),
    )
    _ex11_feedback(4)

    # Q5
    st.markdown(
        "### 5. Construis un modèle du dioxyde d’azote et donne sa formule."
    )
    st.caption(
        "Pour cette première version, le modèle attendu doit aussi respecter "
        "l’organisation des atomes et les liaisons représentées."
    )
    q5_state = render_ex11_builder(generation)
    if isinstance(q5_state, dict):
        st.session_state["ex11_q5_component_state"] = q5_state
        st.session_state["ex11_q5_correct"] = bool(q5_state.get("success"))
        if q5_state.get("success"):
            st.success("✅ Modèle construit et formule correcte.")

    # Q6
    st.markdown(
        "### 6. Le modèle ci-dessous représente le protoxyde d’azote. "
        "Écris sa formule."
    )
    st.markdown(
        """
        <div class="ex11-rule">
          <span><strong style="color:#2c8be6">●</strong> bleu = azote</span>
          <span><strong style="color:#e53935">●</strong> rouge = oxygène</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(_ex11_n2o_model_html(), unsafe_allow_html=True)

    st.text_input(
        "Formule du protoxyde d’azote",
        key=f"ex11_q6_{generation}",
        placeholder="Formule",
        disabled=bool(st.session_state.get("ex11_q6_correct", False)),
    )
    st.button(
        "Valider la question 6",
        key="ex11_validate_q6",
        use_container_width=True,
        on_click=_ex11_validate_q6,
        disabled=bool(st.session_state.get("ex11_q6_correct", False)),
    )
    _ex11_feedback(6)

    completed = sum(
        [
            int(bool(st.session_state.get("ex11_q1_correct", False))),
            int(bool(st.session_state.get("ex11_q2_correct", False))),
            int(bool(st.session_state.get("ex11_q3_correct", False))),
            int(bool(st.session_state.get("ex11_q4_correct", False))),
            int(bool(st.session_state.get("ex11_q5_correct", False))),
            int(bool(st.session_state.get("ex11_q6_correct", False))),
        ]
    )

    st.markdown("### Ton avancement")
    st.progress(completed / 6)
    st.write(f"**{completed} / 6 questions terminées**")

    c_reset, _ = st.columns([1.3, 4.7])
    with c_reset:
        if st.button(
            "↻ Recommencer",
            key="restart_ex11",
            use_container_width=True,
        ):
            _ex11_restart()
            st.rerun()

    if completed == 6:
        q3_final = st.session_state.get("ex11_q3_component_state") or {}
        q5_final = st.session_state.get("ex11_q5_component_state") or {}

        total_errors = sum(
            int(st.session_state.get(f"ex11_q{i}_errors", 0))
            for i in (1, 2, 4, 6)
        )
        total_errors += int(q3_final.get("errors", 0) or 0)
        total_errors += int(q5_final.get("errors", 0) or 0)

        if total_errors == 0:
            st.success("🎉 Exercice terminé sans erreur.")
        else:
            st.warning(
                f"📊 Exercice terminé avec {total_errors} erreur(s) au cours du travail."
            )

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex11_result_saved", False)
        ):
            score = round(100 * 6 / max(6, 6 + total_errors))
            record_training_result(
                student,
                "exercise11_nitrous_oxide",
                score,
                6,
                6,
                errors=total_errors,
            )
            st.session_state["ex11_result_saved"] = True




# ============================================================
# EXERCICE 12 — CAFÉINE
# ============================================================

def _ex12_validate_q1():
    generation = int(st.session_state.get("ex12_generation", 0))

    values = {
        "carbone": _ex10_int(st.session_state.get(f"ex12_q1_c_{generation}", "")),
        "hydrogène": _ex10_int(st.session_state.get(f"ex12_q1_h_{generation}", "")),
        "azote": _ex10_int(st.session_state.get(f"ex12_q1_n_{generation}", "")),
        "oxygène": _ex10_int(st.session_state.get(f"ex12_q1_o_{generation}", "")),
    }

    if any(v is None for v in values.values()):
        st.session_state["ex12_q1_feedback"] = "empty"
        st.session_state["ex12_q1_wrong_fields"] = []
        return

    expected = {
        "carbone": 8,
        "hydrogène": 10,
        "azote": 4,
        "oxygène": 2,
    }

    wrong = [
        label for label, expected_value in expected.items()
        if values[label] != expected_value
    ]

    st.session_state["ex12_q1_wrong_fields"] = wrong

    if not wrong:
        st.session_state["ex12_q1_correct"] = True
        st.session_state["ex12_q1_feedback"] = "correct"
    else:
        st.session_state["ex12_q1_correct"] = False
        st.session_state["ex12_q1_errors"] = int(
            st.session_state.get("ex12_q1_errors", 0)
        ) + 1
        st.session_state["ex12_q1_feedback"] = "wrong"


def _ex12_validate_q2():
    generation = int(st.session_state.get("ex12_generation", 0))
    value = _ex10_int(st.session_state.get(f"ex12_q2_{generation}", ""))

    if value is None:
        st.session_state["ex12_q2_feedback"] = "empty"
        return

    if value == 4:
        st.session_state["ex12_q2_correct"] = True
        st.session_state["ex12_q2_feedback"] = "correct"
    else:
        st.session_state["ex12_q2_correct"] = False
        st.session_state["ex12_q2_errors"] = int(
            st.session_state.get("ex12_q2_errors", 0)
        ) + 1
        st.session_state["ex12_q2_feedback"] = "wrong"


def _ex12_validate_q3():
    generation = int(st.session_state.get("ex12_generation", 0))
    value = _ex10_int(st.session_state.get(f"ex12_q3_{generation}", ""))

    if value is None:
        st.session_state["ex12_q3_feedback"] = "empty"
        return

    if value == 24:
        st.session_state["ex12_q3_correct"] = True
        st.session_state["ex12_q3_feedback"] = "correct"
    else:
        st.session_state["ex12_q3_correct"] = False
        st.session_state["ex12_q3_errors"] = int(
            st.session_state.get("ex12_q3_errors", 0)
        ) + 1
        st.session_state["ex12_q3_feedback"] = "wrong"


def _ex12_feedback(question):
    feedback = st.session_state.get(f"ex12_q{question}_feedback")
    errors = int(st.session_state.get(f"ex12_q{question}_errors", 0))

    if feedback == "correct":
        messages = {
            1: "✅ Bonne lecture de la formule : C₈H₁₀N₄O₂.",
            2: "✅ Il y a 4 sortes d’atomes différentes : C, H, N et O.",
            3: "✅ La molécule contient 24 atomes au total.",
        }
        st.success(messages[question])
        return

    if feedback == "empty":
        st.warning("✏️ Complète la réponse avant de valider.")
        return

    if feedback != "wrong":
        return

    if question == 1:
        wrong = st.session_state.get("ex12_q1_wrong_fields", [])
        if wrong:
            st.warning(
                "💡 Relis l’indice placé après le symbole de : "
                + ", ".join(wrong)
                + "."
            )
        else:
            st.warning("💡 Relis les indices placés après chaque symbole.")
    elif question == 2:
        if errors == 1:
            st.warning("💡 Compte les symboles chimiques différents présents dans la formule.")
        else:
            st.warning("🔎 Les symboles présents sont C, H, N et O.")
    elif question == 3:
        if errors == 1:
            st.warning("💡 Additionne le nombre de tous les atomes indiqués par les indices.")
        else:
            st.warning("🔎 Additionne 8 + 10 + 4 + 2.")


def reset_exercise12():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex12_"):
            st.session_state.pop(key, None)


def page_exercise12_caffeine():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise12_caffeine"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Caféine</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">☕ Exercice 12 — Caféine</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="
          background:#f5f9ff;border:1px solid #cfe0fb;border-radius:16px;
          padding:1rem 1.1rem;margin:.7rem 0 1rem;font-size:1.12rem;
          line-height:1.55;color:#314b69;">
          Voici la formule de la molécule de caféine :
          <span style="font-size:1.5rem;font-weight:900;color:#173b70;">
          C<sub>8</sub>H<sub>10</sub>N<sub>4</sub>O<sub>2</sub>
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    generation = int(st.session_state.get("ex12_generation", 0))

    st.markdown("### 1. Détaille la composition de la molécule.")
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        st.text_input(
            "Nombre d’atomes de carbone",
            key=f"ex12_q1_c_{generation}",
            disabled=bool(st.session_state.get("ex12_q1_correct", False)),
        )
    with c2:
        st.text_input(
            "Nombre d’atomes d’hydrogène",
            key=f"ex12_q1_h_{generation}",
            disabled=bool(st.session_state.get("ex12_q1_correct", False)),
        )
    with c3:
        st.text_input(
            "Nombre d’atomes d’azote",
            key=f"ex12_q1_n_{generation}",
            disabled=bool(st.session_state.get("ex12_q1_correct", False)),
        )
    with c4:
        st.text_input(
            "Nombre d’atomes d’oxygène",
            key=f"ex12_q1_o_{generation}",
            disabled=bool(st.session_state.get("ex12_q1_correct", False)),
        )

    st.button(
        "Valider la composition",
        key="ex12_validate_q1",
        use_container_width=True,
        type="primary",
        on_click=_ex12_validate_q1,
        disabled=bool(st.session_state.get("ex12_q1_correct", False)),
    )
    _ex12_feedback(1)

    st.markdown("### 2. Combien y a-t-il de sortes d’atomes différentes ?")
    st.text_input(
        "Nombre de sortes d’atomes",
        key=f"ex12_q2_{generation}",
        disabled=bool(st.session_state.get("ex12_q2_correct", False)),
    )
    st.button(
        "Valider la question 2",
        key="ex12_validate_q2",
        use_container_width=True,
        on_click=_ex12_validate_q2,
        disabled=bool(st.session_state.get("ex12_q2_correct", False)),
    )
    _ex12_feedback(2)

    st.markdown("### 3. Quel est le nombre total d’atomes contenus dans la molécule ?")
    st.text_input(
        "Nombre total d’atomes",
        key=f"ex12_q3_{generation}",
        disabled=bool(st.session_state.get("ex12_q3_correct", False)),
    )
    st.button(
        "Valider la question 3",
        key="ex12_validate_q3",
        use_container_width=True,
        on_click=_ex12_validate_q3,
        disabled=bool(st.session_state.get("ex12_q3_correct", False)),
    )
    _ex12_feedback(3)

    completed = sum(
        int(bool(st.session_state.get(f"ex12_q{i}_correct", False)))
        for i in (1, 2, 3)
    )

    st.markdown("### Ton avancement")
    st.progress(completed / 3)
    st.write(f"**{completed} / 3 questions réussies**")

    if st.button("↻ Recommencer", key="restart_ex12"):
        reset_exercise12()
        st.rerun()

    if completed == 3:
        st.success("🎉 Exercice terminé.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex12_result_saved", False)
        ):
            errors = sum(
                int(st.session_state.get(f"ex12_q{i}_errors", 0))
                for i in (1, 2, 3)
            )
            score = round(100 * 3 / max(3, 3 + errors))
            record_training_result(
                student,
                "exercise12_caffeine",
                score,
                3,
                3,
                errors=errors,
            )
            st.session_state["ex12_result_saved"] = True


# ============================================================
# EXERCICE 13 — NOMS ET FORMULES
# ============================================================

EXERCISE13_ITEMS = [
    {
        "id": "h2o",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 13/H2O.png"),
            Path("assets/chapitre_1/exercice_13/H2O.png"),
        ],
        "name_answers": {"eau", "molecule d eau", "molécule d eau"},
        "formula": "H2O",
        "hint": "Le modèle contient un atome d’oxygène et deux atomes d’hydrogène.",
    },
    {
        "id": "co2",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 13/CO2.png"),
            Path("assets/chapitre_1/exercice_13/CO2.png"),
        ],
        "name_answers": {"dioxyde de carbone"},
        "formula": "CO2",
        "hint": "Le modèle contient un atome de carbone et deux atomes d’oxygène.",
    },
    {
        "id": "n2",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 13/N2.png"),
            Path("assets/chapitre_1/exercice_13/N2.png"),
        ],
        "name_answers": {"diazote"},
        "formula": "N2",
        "hint": "Il s’agit d’une molécule constituée de deux atomes d’azote.",
    },
    {
        "id": "h2",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 13/H2.png"),
            Path("assets/chapitre_1/exercice_13/H2.png"),
        ],
        "name_answers": {"dihydrogene", "dihydrogène"},
        "formula": "H2",
        "hint": "Il s’agit d’une molécule constituée de deux atomes d’hydrogène.",
    },
]


def _exercise_image(candidates):
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@st.cache_data(show_spinner=False)
def _uniform_molecule_image_bytes(path_string):
    """
    Prépare les modèles moléculaires avec une véritable échelle visuelle commune.

    La version précédente redimensionnait chaque molécule pour remplir presque
    toute la zone disponible. Cela alignait bien les cadres, mais une molécule
    diatomique pouvait paraître beaucoup plus grosse qu'une autre.

    Ici :
    - les marges blanches des fichiers sources sont d'abord retirées ;
    - chaque famille de modèle reçoit ensuite une taille cible adaptée ;
    - les molécules diatomiques H2, N2 et Cl2 utilisent exactement la même
      largeur cible ;
    - les modèles à 3 ou 5 atomes occupent naturellement davantage de place ;
    - tous les fichiers sont finalement placés sur le même canevas.
    """
    path = Path(path_string)

    with Image.open(path) as source:
        image = source.convert("RGB")

    width, height = image.size

    # Détermination du fond à partir des quatre coins.
    corners = [
        image.getpixel((0, 0)),
        image.getpixel((max(0, width - 1), 0)),
        image.getpixel((0, max(0, height - 1))),
        image.getpixel((max(0, width - 1), max(0, height - 1))),
    ]
    background_rgb = tuple(
        int(round(sum(pixel[channel] for pixel in corners) / len(corners)))
        for channel in range(3)
    )

    background = Image.new("RGB", image.size, background_rgb)
    difference = ImageChops.difference(image, background).convert("L")

    # On élimine le fond quasi blanc tout en gardant les ombres utiles.
    mask = difference.point(lambda value: 255 if value > 12 else 0)
    bbox = mask.getbbox()

    if bbox:
        left, top, right, bottom = bbox
        detected_w = max(1, right - left)
        detected_h = max(1, bottom - top)

        # Marge réduite : on conserve juste assez d'air pour ne pas couper
        # les ombres, mais on évite le grand halo blanc autour du modèle.
        pad_x = max(6, int(detected_w * 0.02))
        pad_y = max(6, int(detected_h * 0.02))

        left = max(0, left - pad_x)
        top = max(0, top - pad_y)
        right = min(width, right + pad_x)
        bottom = min(height, bottom + pad_y)

        molecule = image.crop((left, top, right, bottom))
    else:
        molecule = image

    # --------------------------------------------------------
    # ÉCHELLE COMMUNE
    # --------------------------------------------------------
    # Les dimensions ci-dessous ne cherchent PAS à donner la même largeur
    # à toutes les molécules. Elles cherchent à donner une taille comparable
    # aux boules représentant les atomes.
    #
    # H2, N2 et Cl2 sont diatomiques : même largeur cible.
    # CO2 est linéaire avec 3 atomes : il est donc plus large.
    # H2O est coudée : largeur intermédiaire.
    # CH4 est tridimensionnelle : largeur intermédiaire et hauteur plus grande.
    filename = path.name.lower()

    target_sizes = {
        "h2.png":  (300, 190),
        "n2.png":  (300, 190),
        "cl2.png": (300, 190),
        "co2.png": (430, 190),
        "h2o.png": (330, 230),
        "ch4.png": (335, 270),
    }

    target_w, target_h = target_sizes.get(filename, (340, 230))

    # On conserve strictement les proportions de l'image source.
    scale = min(
        target_w / max(1, molecule.width),
        target_h / max(1, molecule.height),
    )
    new_w = max(1, int(round(molecule.width * scale)))
    new_h = max(1, int(round(molecule.height * scale)))

    molecule = molecule.resize(
        (new_w, new_h),
        Image.Resampling.LANCZOS,
    )

    # Même canevas pour tous, mais plus compact :
    # on gagne de la place verticale tout en gardant l'alignement des champs.
    canvas_w, canvas_h = 620, 320
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))

    x = (canvas_w - molecule.width) // 2
    y = (canvas_h - molecule.height) // 2
    canvas.paste(molecule, (x, y))

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_uniform_molecule_image(image_path):
    """
    Affiche les modèles sur un canevas identique et compact.
    Les champs Nom/Formule restent parfaitement alignés entre colonnes,
    avec beaucoup moins de blanc autour des molécules.
    """
    image_bytes = _uniform_molecule_image_bytes(str(image_path))
    st.image(image_bytes, use_container_width=True)



def _chem_name_norm(value):
    return _ex8_norm(value).replace("'", " ")


def _ex13_validate_item(index):
    generation = int(st.session_state.get("ex13_generation", 0))
    item = EXERCISE13_ITEMS[index]

    name = _chem_name_norm(
        st.session_state.get(f"ex13_name_{index}_{generation}", "")
    )
    formula = _chem_formula_norm(
        st.session_state.get(f"ex13_formula_{index}_{generation}", "")
    )

    if not name or not formula:
        st.session_state[f"ex13_feedback_{index}"] = "empty"
        return

    accepted_names = {_chem_name_norm(v) for v in item["name_answers"]}
    name_ok = name in accepted_names
    formula_ok = formula == item["formula"]

    if name_ok and formula_ok:
        st.session_state[f"ex13_correct_{index}"] = True
        st.session_state[f"ex13_feedback_{index}"] = "correct"
    else:
        st.session_state[f"ex13_correct_{index}"] = False
        st.session_state[f"ex13_errors_{index}"] = int(
            st.session_state.get(f"ex13_errors_{index}", 0)
        ) + 1
        st.session_state[f"ex13_feedback_{index}"] = {
            "name_ok": name_ok,
            "formula_ok": formula_ok,
        }


def _ex13_render_item(index):
    item = EXERCISE13_ITEMS[index]
    generation = int(st.session_state.get("ex13_generation", 0))
    correct = bool(st.session_state.get(f"ex13_correct_{index}", False))

    image_path = _exercise_image(item["image_candidates"])

    st.markdown(
        f"#### Modèle {chr(ord('a') + index)}"
    )

    if image_path is not None:
        _render_uniform_molecule_image(image_path)
    else:
        st.warning(
            f"Image manquante pour le modèle {chr(ord('a') + index)}."
        )

    st.text_input(
        "Nom de la molécule",
        key=f"ex13_name_{index}_{generation}",
        disabled=correct,
    )
    st.text_input(
        "Formule",
        key=f"ex13_formula_{index}_{generation}",
        disabled=correct,
    )

    st.button(
        "Valider",
        key=f"ex13_validate_{index}",
        use_container_width=True,
        on_click=_ex13_validate_item,
        args=(index,),
        disabled=correct,
    )

    feedback = st.session_state.get(f"ex13_feedback_{index}")
    errors = int(st.session_state.get(f"ex13_errors_{index}", 0))

    if feedback == "empty":
        st.warning("✏️ Complète le nom et la formule.")
    elif feedback == "correct":
        st.success("✅ Nom et formule corrects.")
    elif isinstance(feedback, dict):
        name_ok = feedback.get("name_ok", False)
        formula_ok = feedback.get("formula_ok", False)

        if name_ok and not formula_ok:
            st.warning("💡 Le nom est correct. Revois la formule.")
        elif formula_ok and not name_ok:
            st.warning("💡 La formule est correcte. Revois le nom.")
        elif errors == 1:
            st.warning("💡 Observe les couleurs et compte les atomes du modèle.")
        else:
            st.warning("🔎 " + item["hint"])


def reset_exercise13():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex13_"):
            st.session_state.pop(key, None)


def page_exercise13_names_formulas():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise13_names_formulas"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        """
        <style>
        /* Exercice 13 : mêmes espacements dans les deux colonnes. */
        .ex13-model-spacer {
            height: 0;
            margin: 0;
            padding: 0;
        }

        div[data-testid="stTextInput"] input {
            font-size: 1.08rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Noms et formules</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🧬 Exercice 13 — Noms et formules</div>',
        unsafe_allow_html=True,
    )
    st.info(
        "Pour chaque modèle, indique le nom de la molécule et sa formule."
    )

    for row_start in (0, 2):
        cols = st.columns(2, gap="large")
        for offset, col in enumerate(cols):
            index = row_start + offset
            with col:
                _ex13_render_item(index)

    completed = sum(
        int(bool(st.session_state.get(f"ex13_correct_{i}", False)))
        for i in range(len(EXERCISE13_ITEMS))
    )

    st.markdown("### Ton avancement")
    st.progress(completed / len(EXERCISE13_ITEMS))
    st.write(
        f"**{completed} / {len(EXERCISE13_ITEMS)} modèles réussis**"
    )

    if st.button("↻ Recommencer", key="restart_ex13"):
        reset_exercise13()
        st.rerun()

    if completed == len(EXERCISE13_ITEMS):
        st.success("🎉 Exercice terminé.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex13_result_saved", False)
        ):
            errors = sum(
                int(st.session_state.get(f"ex13_errors_{i}", 0))
                for i in range(len(EXERCISE13_ITEMS))
            )
            score = round(
                100 * len(EXERCISE13_ITEMS)
                / max(len(EXERCISE13_ITEMS), len(EXERCISE13_ITEMS) + errors)
            )
            record_training_result(
                student,
                "exercise13_names_formulas",
                score,
                len(EXERCISE13_ITEMS),
                len(EXERCISE13_ITEMS),
                errors=errors,
            )
            st.session_state["ex13_result_saved"] = True


# ============================================================
# EXERCICE 14 — FORMULES DE MOLÉCULES
# ============================================================

EXERCISE14_ITEMS = [
    {
        "id": "ch4",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 14/CH4.png"),
            Path("assets/chapitre_1/exercice_14/CH4.png"),
        ],
        "formula": "CH4",
        "hint": "Compte le nombre d’atomes de carbone et d’hydrogène.",
    },
    {
        "id": "cl2",
        "image_candidates": [
            Path("assets/chapitre_1/exercice 14/Cl2.png"),
            Path("assets/chapitre_1/exercice_14/Cl2.png"),
        ],
        "formula": "Cl2",
        "hint": "Le symbole du chlore est Cl. Le modèle montre deux atomes de chlore.",
    },
]


def _ex14_validate_item(index):
    generation = int(st.session_state.get("ex14_generation", 0))
    item = EXERCISE14_ITEMS[index]

    formula = _chem_formula_norm(
        st.session_state.get(f"ex14_formula_{index}_{generation}", "")
    )

    if not formula:
        st.session_state[f"ex14_feedback_{index}"] = "empty"
        return

    if formula == item["formula"]:
        st.session_state[f"ex14_correct_{index}"] = True
        st.session_state[f"ex14_feedback_{index}"] = "correct"
    else:
        st.session_state[f"ex14_correct_{index}"] = False
        st.session_state[f"ex14_errors_{index}"] = int(
            st.session_state.get(f"ex14_errors_{index}", 0)
        ) + 1
        st.session_state[f"ex14_feedback_{index}"] = "wrong"


def reset_exercise14():
    for key in list(st.session_state.keys()):
        if str(key).startswith("ex14_"):
            st.session_state.pop(key, None)


def page_exercise14_molecule_formulas():
    hero()
    back_button("exercise_topics")

    if not resource_is_available_for_current_user("exercise14_molecule_formulas"):
        st.warning("Cet exercice n'est pas encore ouvert pour ta classe.")
        return

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › '
        'Chapitre 1 › Séance 2 › Formules de molécules</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🔎 Exercice 14 — Formules de molécules</div>',
        unsafe_allow_html=True,
    )
    st.info(
        "Observe chaque modèle et écris la formule de la molécule représentée."
    )

    generation = int(st.session_state.get("ex14_generation", 0))
    cols = st.columns(2, gap="large")

    for index, col in enumerate(cols):
        item = EXERCISE14_ITEMS[index]
        correct = bool(st.session_state.get(f"ex14_correct_{index}", False))
        image_path = _exercise_image(item["image_candidates"])

        with col:
            st.markdown(f"#### Modèle {chr(ord('a') + index)}")

            if image_path is not None:
                _render_uniform_molecule_image(image_path)
            else:
                st.warning("Image manquante.")

            st.text_input(
                "Formule",
                key=f"ex14_formula_{index}_{generation}",
                disabled=correct,
            )

            st.button(
                "Valider",
                key=f"ex14_validate_{index}",
                use_container_width=True,
                on_click=_ex14_validate_item,
                args=(index,),
                disabled=correct,
            )

            feedback = st.session_state.get(f"ex14_feedback_{index}")
            errors = int(st.session_state.get(f"ex14_errors_{index}", 0))

            if feedback == "empty":
                st.warning("✏️ Écris une formule.")
            elif feedback == "correct":
                st.success("✅ Bonne formule.")
            elif feedback == "wrong":
                if errors == 1:
                    st.warning("💡 Recompte les atomes représentés.")
                else:
                    st.warning("🔎 " + item["hint"])

    completed = sum(
        int(bool(st.session_state.get(f"ex14_correct_{i}", False)))
        for i in range(len(EXERCISE14_ITEMS))
    )

    st.markdown("### Ton avancement")
    st.progress(completed / len(EXERCISE14_ITEMS))
    st.write(
        f"**{completed} / {len(EXERCISE14_ITEMS)} modèles réussis**"
    )

    if st.button("↻ Recommencer", key="restart_ex14"):
        reset_exercise14()
        st.rerun()

    if completed == len(EXERCISE14_ITEMS):
        st.success("🎉 Exercice terminé.")

        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("ex14_result_saved", False)
        ):
            errors = sum(
                int(st.session_state.get(f"ex14_errors_{i}", 0))
                for i in range(len(EXERCISE14_ITEMS))
            )
            score = round(
                100 * len(EXERCISE14_ITEMS)
                / max(len(EXERCISE14_ITEMS), len(EXERCISE14_ITEMS) + errors)
            )
            record_training_result(
                student,
                "exercise14_molecule_formulas",
                score,
                len(EXERCISE14_ITEMS),
                len(EXERCISE14_ITEMS),
                errors=errors,
            )
            st.session_state["ex14_result_saved"] = True



def reset_states_matter_training():
    for key in list(st.session_state.keys()):
        if (
            str(key).startswith("states_q_")
            or str(key).startswith("states_checked_")
            or str(key).startswith("states_last_wrong_")
        ):
            st.session_state.pop(key, None)
    st.session_state.pop("states_completed", None)
    st.session_state.pop("states_error_count", None)
    st.session_state.pop("states_result_saved", None)


def page_states_matter_training():
    hero()
    back_button("exercise_topics")

    if not states_matter_available_for_current_user():
        st.warning("Cette notion n'est pas encore ouverte pour votre classe.")
        return

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Exercices › États de la matière</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title">🧊 États de la matière</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Réponds à chaque question puis valide. En cas d'erreur, une aide apparaît : "
        "tu peux ensuite modifier ta réponse et réessayer."
    )

    correct_count = 0
    answered_count = 0

    for i, item in enumerate(STATES_MATTER_QUESTIONS, start=1):
        st.markdown(f"### Question {i} / {len(STATES_MATTER_QUESTIONS)}")
        st.write(item["question"])

        answer_key = f"states_q_{i}"
        checked_key = f"states_checked_{i}"

        selected = st.radio(
            "Choisis une réponse",
            ["— Choisir —"] + item["choices"],
            key=answer_key,
            label_visibility="collapsed",
        )

        if st.button("Valider", key=f"validate_states_{i}", disabled=selected == "— Choisir —"):
            st.session_state[checked_key] = True
            if selected != item["answer"]:
                wrong_token = f"{i}:{selected}"
                last_wrong_key = f"states_last_wrong_{i}"
                if st.session_state.get(last_wrong_key) != wrong_token:
                    st.session_state["states_error_count"] = int(
                        st.session_state.get("states_error_count", 0)
                    ) + 1
                    st.session_state[last_wrong_key] = wrong_token

        checked = st.session_state.get(checked_key, False)

        if checked and selected != "— Choisir —":
            answered_count += 1
            if selected == item["answer"]:
                correct_count += 1
                st.success("✅ Bonne réponse !")
                st.info(item["explanation"])
            else:
                st.error("❌ Ce n'est pas encore la bonne réponse.")
                st.warning("💡 Indice : " + item["hint"])
                st.caption("Modifie ta réponse puis clique de nouveau sur « Valider ».")

        st.divider()

    st.markdown("### Ton avancement")
    st.progress(correct_count / len(STATES_MATTER_QUESTIONS))
    st.write(f"**{correct_count} / {len(STATES_MATTER_QUESTIONS)} réponses correctes actuellement.**")

    if correct_count == len(STATES_MATTER_QUESTIONS):
        st.success("🎉 Bravo ! Tu as réussi tout l'entraînement « États de la matière ».")
        st.session_state.states_completed = True

        # Le résultat n'est enregistré qu'une fois par réalisation complète.
        student = st.session_state.get("app_student")
        if (
            st.session_state.get("app_user_type") == "student"
            and student
            and not st.session_state.get("states_result_saved", False)
        ):
            errors = int(st.session_state.get("states_error_count", 0))
            # Indicateur de maîtrise : 100 % sans erreur, puis baisse progressive.
            score = round(
                100 * len(STATES_MATTER_QUESTIONS)
                / (len(STATES_MATTER_QUESTIONS) + errors)
            )
            record_training_result(
                student,
                "exercise_states_matter",
                score,
                len(STATES_MATTER_QUESTIONS),
                len(STATES_MATTER_QUESTIONS),
                errors=errors,
            )
            st.session_state.states_result_saved = True

    if st.button("🔄 Recommencer tout l'entraînement", use_container_width=False):
        reset_states_matter_training()
        st.rerun()

def resource_is_available_for_current_user(resource_id):
    """Professeur : tout le catalogue. Élève pilote : uniquement les ressources ouvertes pour sa classe."""
    if st.session_state.get("app_user_type") == "teacher":
        return True
    if st.session_state.get("app_user_type") != "student":
        return False
    student = st.session_state.get("app_student") or {}
    teacher_id = student.get("_teacher_id")
    if not content_pilot_enabled_for_teacher(teacher_id, ""):
        return True
    return content_is_open_for_class(resource_id, student.get("class_name", ""), teacher_id)


def page_free_theme():
    hero()
    back_button("free_activity")

    st.markdown(
        '<div class="breadcrumb">Accueil › Mon espace d’entraînement › Dominos › Choix du thème</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-title">Dominos — choisissez un thème</div>', unsafe_allow_html=True)

    catalog = [
        ("🔵", "Molécules", "Formules, modèles moléculaires et composition de la matière.", "card-blue", "theme_molecules"),
        ("🧪", "Verrerie", "Reconnaître le matériel de laboratoire à partir de son illustration.", "card-cyan", "theme_glassware"),
        ("➕➖", "Ions", "Associer la formule d'un ion à son nom.", "card-green", "theme_ions"),
        ("⚡", "Électricité", "Passer du montage électrique au schéma normalisé et réciproquement.", "card-orange", "theme_elec"),
    ]
    themes = [item for item in catalog if resource_is_available_for_current_user(RESOURCE_BY_THEME[item[1]])]

    if not themes:
        st.info("Aucun domino n'est encore ouvert pour votre classe.")
        return

    cols = st.columns(min(4, len(themes)))
    for i, (icon, title, description, color, key) in enumerate(themes):
        with cols[i]:
            nav_card(icon, title, description, color)
            if st.button(f"Choisir {title}", key=key, use_container_width=True):
                st.session_state.selected_theme = title
                go("free_level")


def page_free_level():
    hero()
    back_button("free_theme")

    theme = st.session_state.get("selected_theme", "Molécules")
    resource_id = RESOURCE_BY_THEME.get(theme)
    if resource_id and not resource_is_available_for_current_user(resource_id):
        st.warning("Ce domino n'est pas ouvert pour votre classe.")
        st.button("← Retour aux dominos", on_click=set_page, args=("free_theme",))
        return
    theme_levels = levels_for_theme(theme)

    st.markdown(
        f'<div class="breadcrumb">Accueil › Mon espace d’entraînement › Dominos › {theme} › Niveau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Choisissez votre niveau</div>',
        unsafe_allow_html=True,
    )

    if theme == "Électricité":
        for row_start in range(0, len(theme_levels), 3):
            row_levels = theme_levels[row_start:row_start + 3]
            cols = st.columns(3)

            for i, level in enumerate(row_levels):
                with cols[i]:
                    nav_card(
                        LEVELS[level]["emoji"],
                        level,
                        "Montage réel ↔ schéma électrique normalisé.",
                        "card-orange",
                    )
                    if st.button(
                        f"Jouer — {level}",
                        key=f"level_{theme}_{level}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_level = level
                        init_game(level, "free")
                        go("free_game")

    elif theme == "Verrerie":
        cols = st.columns(2)
        for i, level in enumerate(theme_levels):
            with cols[i]:
                descriptions = {
                    "Verrerie — Essentiel": "8 matériels courants à reconnaître.",
                    "Verrerie — Complet": "13 matériels de laboratoire à reconnaître.",
                }
                nav_card(
                    LEVELS[level]["emoji"],
                    level.replace("Verrerie — ", ""),
                    descriptions.get(level, "Reconnaître le matériel de laboratoire."),
                    "card-cyan",
                )
                if st.button(
                    f"Jouer — {level.replace('Verrerie — ', '')}",
                    key=f"level_{theme}_{level}",
                    use_container_width=True,
                ):
                    st.session_state.selected_level = level
                    init_game(level, "free")
                    go("free_game")

    elif theme == "Ions":
        descriptions = {
            "Ions — Essentiel": "10 ions usuels : formule ↔ nom.",
            "Ions — Complet": "Les 18 ions de la liste : formule ↔ nom.",
            "Ions — Composition": "Écriture nucléaire ↔ protons, neutrons et électrons.",
            "Ions — Charges et électrons": "18 dominos bleus : atome/ion ↔ protons et électrons.",
        }

        for row_start in range(0, len(theme_levels), 2):
            row_levels = theme_levels[row_start:row_start + 2]
            cols = st.columns(2)

            for i, level in enumerate(row_levels):
                with cols[i]:
                    nav_card(
                        LEVELS[level]["emoji"],
                        level.replace("Ions — ", ""),
                        descriptions.get(level, "Associer les représentations des ions."),
                        "card-green",
                    )
                    if st.button(
                        f"Jouer — {level.replace('Ions — ', '')}",
                        key=f"level_{theme}_{level}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_level = level
                        init_game(level, "free")
                        go("free_game")

    else:
        classic = [x for x in theme_levels if "textes" not in x]
        enriched = [x for x in theme_levels if "textes" in x]

        st.markdown("### 🧪 Formules ↔ modèles moléculaires")
        cols = st.columns(4)
        for i, level in enumerate(classic):
            with cols[i]:
                colors = ["card-green", "card-orange", "card-pink", "card-purple"]
                nav_card(
                    LEVELS[level]["emoji"],
                    level,
                    "Associer modèles moléculaires et écritures chimiques.",
                    colors[i % len(colors)],
                )
                if st.button(
                    f"Jouer — {level}",
                    key=f"level_{theme}_{level}",
                    use_container_width=True,
                ):
                    st.session_state.selected_level = level
                    init_game(level, "free")
                    go("free_game")

        st.markdown("### 📝 Formules ↔ modèles ↔ descriptions")
        cols = st.columns(4)
        for i, level in enumerate(enriched):
            with cols[i]:
                colors = ["card-green", "card-orange", "card-pink", "card-purple"]
                nav_card(
                    LEVELS[level]["emoji"],
                    level.replace(" + textes", ""),
                    "Ajouter le vocabulaire scientifique aux associations.",
                    colors[i % len(colors)],
                )
                if st.button(
                    f"Jouer — {level.replace(' + textes', '')}",
                    key=f"level_{theme}_{level}",
                    use_container_width=True,
                ):
                    st.session_state.selected_level = level
                    init_game(level, "free")
                    go("free_game")


def page_free_game():
    hero()
    back_button("free_level")

    theme = st.session_state.get("selected_theme", "Molécules")
    default_level = levels_for_theme(theme)[0]
    level = st.session_state.get("selected_level", default_level)

    st.markdown(
        f'<div class="breadcrumb">Accueil › Mon espace d’entraînement › Dominos › {theme} › {level}</div>',
        unsafe_allow_html=True,
    )

    st.subheader(
        f"🁢 Dominos — {theme} · {LEVELS[level]['emoji']} {level}"
    )

    domino_game(level, suffix="free")
    game_credit(theme)


# ============================================================
# DÉFI ÉLÈVE
# ============================================================

def page_challenge():
    hero()
    back_button("home")

    user_type = st.session_state.get("app_user_type")

    # Un élève identifié à l'entrée reste identifié pendant toute sa session.
    if user_type == "student":
        session_student = st.session_state.get("app_student")
        if session_student:
            st.session_state.challenge_student = session_student

    student = st.session_state.get("challenge_student")
    challenge = st.session_state.get("active_challenge")

    st.markdown(
        '<div class="breadcrumb">Accueil › Participer à un défi</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">🏆 Participer à un défi</div>',
        unsafe_allow_html=True,
    )

    # Le professeur peut tester un défi en choisissant ponctuellement un élève.
    # L'élève, lui, n'a jamais à ressaisir son code personnel ici.
    if not student:
        if user_type == "teacher":
            st.info(
                "Mode professeur : pour tester un défi comme un élève, "
                "saisissez ponctuellement le code personnel d'un élève."
            )

            student_code = st.text_input(
                "Code élève de test",
                max_chars=6,
                placeholder="Ex. K7P4QM",
                key="teacher_test_student_code",
            )

            if st.button(
                "Continuer",
                type="primary",
                use_container_width=True,
                key="teacher_identify_test_student",
            ):
                found = find_student_by_code(student_code)
                if found:
                    st.session_state.challenge_student = found
                    st.rerun()
                else:
                    st.error("Code élève inconnu.")
            return

        st.error("Aucun élève identifié. Déconnectez-vous puis reconnectez-vous avec votre code personnel.")
        return

    st.success(
        f"Bonjour **{student['first_name']} {student['last_initial']}.** "
        f"— classe **{student['class_name']}**"
    )

    if not challenge:
        used_code = st.text_input(
            "Code du défi",
            max_chars=4,
            placeholder="Ex. 4827",
            key="challenge_code_input",
        )

        if st.button(
            "🏆 Rejoindre le défi",
            type="primary",
            use_container_width=True,
        ):
            found = find_open_challenge(used_code, student.get("_teacher_id"))

            if not found:
                st.error("Ce défi n'existe pas ou il est fermé.")
            elif found["class_name"] != student["class_name"]:
                st.error("Ce défi n'est pas destiné à votre classe.")
            elif attempts_used(student, found) >= int(found["max_attempts"]):
                st.error("Toutes les tentatives autorisées ont déjà été utilisées.")
            elif found.get("activity", "Dominos") != "Dominos" or found.get("theme", "Molécules") not in ("Molécules", "Verrerie", "Ions", "Électricité"):
                st.error("Cette activité n'est pas encore disponible dans cette version.")
            else:
                st.session_state.active_challenge = found

                if found.get("mode", "Individuel") == "Collaboratif":
                    st.session_state.pop("collab_team_code", None)
                else:
                    suffix = f"challenge_{found['code']}_{student['id']}"
                    init_game(found["level"], suffix)

                st.rerun()

        if st.session_state.get("app_user_type") == "teacher":
            if st.button(
                "Changer d'élève de test",
                use_container_width=True,
                key="teacher_change_test_student",
            ):
                st.session_state.pop("challenge_student", None)
                st.session_state.pop("active_challenge", None)
                st.rerun()

        return

    st.markdown(
        f"### Défi {challenge['code']} — {challenge['game']}"
    )

    remaining = challenge_remaining_seconds(challenge)

    timing_text = (
        "Sans limite de temps"
        if remaining is None
        else f"Temps restant : {format_remaining_time(remaining)}"
    )

    st.write(
        f"**Classe :** {challenge['class_name']}  ·  "
        f"**Niveau :** {LEVELS[challenge['level']]['emoji']} {challenge['level']}  ·  "
        f"**Tentatives autorisées :** {challenge['max_attempts']}  ·  "
        f"**{timing_text}**"
    )

    game_credit(challenge.get("theme", "Molécules"))

    if challenge.get("mode", "Individuel") == "Collaboratif":
        collaborative_challenge_page(student, challenge)
        return

    suffix = f"challenge_{challenge['code']}_{student['id']}"

    domino_game(
        challenge["level"],
        suffix=suffix,
        challenge=challenge,
        student=student,
    )


# ============================================================
# CONNEXION PROFESSEUR
# ============================================================

def teacher_login():
    """La connexion professeur se fait désormais dans le sas d'entrée général."""
    if st.session_state.get("teacher_authenticated", False):
        return True

    st.warning("Veuillez vous identifier comme professeur depuis l'écran d'entrée.")
    if st.button("Retour à l'identification", use_container_width=True):
        clear_app_session()
        st.rerun()
    return False


# ============================================================
# ESPACE PROFESSEUR
# ============================================================

def teacher_header(title=None):
    st.markdown(
        f"""
        <div class="teacher-band">
            <div class="teacher-band-title">👨‍🏫 Espace professeur — {current_teacher_name()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def set_teacher_section_fast(section):
    """Navigation interne immédiate dans l'espace professeur."""
    st.session_state.teacher_section = section
    st.session_state.page = "teacher"


def set_teacher_page_fast(page):
    """Navigation immédiate vers une grande rubrique de la Ludothèque."""
    st.session_state.page = page


def teacher_logout_fast():
    """Déconnexion immédiate depuis le bandeau professeur."""
    clear_app_session()


def teacher_left_panel(section):
    """
    Navigation principale commune à tous les professeurs activés.

    Hiérarchie visuelle :
    - Accueil
    - Entraînement
    - Défi
    - Espace professeur
        Classes et élèves
        Contenus
        Suivi des élèves
        Création des défis
        Résultats
    - Déconnexion
    """
    section = section or "dashboard"

    with st.container(key="teacher_nav_panel"):
        st.markdown(
            """
            <div class="teacher-left-logo">
                <div class="teacher-left-logo-title">🧪 Ludothèque<br>Physique-Chimie</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --------------------------------------------------------
        # Accueil
        # --------------------------------------------------------
        st.button(
            "🏠  Accueil",
            key="teacher_left_home",
            use_container_width=True,
            on_click=set_teacher_page_fast,
            args=("home",),
        )

        # --------------------------------------------------------
        # Trois espaces principaux : même importance visuelle
        # --------------------------------------------------------
        with st.container(key="teacher_primary_training"):
            st.button(
                "Entraînement",
                key="teacher_left_training",
                use_container_width=True,
                on_click=set_teacher_page_fast,
                args=("free_activity",),
            )

        with st.container(key="teacher_primary_challenge"):
            st.button(
                "Défi",
                key="teacher_left_challenge",
                use_container_width=True,
                on_click=set_teacher_page_fast,
                args=("challenge",),
            )

        if section == "dashboard":
            st.markdown(
                '<div class="teacher-left-primary-active">Espace professeur</div>',
                unsafe_allow_html=True,
            )
        else:
            with st.container(key="teacher_primary_prof"):
                st.button(
                    "Espace professeur",
                    key="teacher_left_dashboard",
                    use_container_width=True,
                    on_click=set_teacher_section_fast,
                    args=("dashboard",),
                )

        # --------------------------------------------------------
        # Sous-rubriques : retrait simple, sans icône ni flèche
        # --------------------------------------------------------
        st.markdown(
            '<div class="teacher-left-tree">',
            unsafe_allow_html=True,
        )

        teacher_items = [
            ("classes_students", "Classes et élèves"),
            ("contents", "Contenus"),
            ("tracking", "Suivi des élèves"),
            ("challenges", "Création des défis"),
            ("results", "Résultats"),
        ]

        for target, label in teacher_items:
            if section == target:
                st.markdown(
                    f'<div class="teacher-left-subactive">{label}</div>',
                    unsafe_allow_html=True,
                )
            else:
                with st.container(key=f"teacher_sub_{target}"):
                    st.button(
                        label,
                        key=f"teacher_left_{target}",
                        use_container_width=True,
                        on_click=set_teacher_section_fast,
                        args=(target,),
                    )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            '<div class="teacher-left-separator"></div>',
            unsafe_allow_html=True,
        )

        st.button(
            "🚪  Déconnexion",
            key="teacher_left_logout",
            use_container_width=True,
            on_click=teacher_logout_fast,
        )



def teacher_dashboard():
    # Titre unique de l'espace professeur.
    teacher_header()

    classes = get_classes()
    students = get_students()
    challenges = get_challenges()
    results = get_results()
    activity_rows = get_activity_log()

    open_challenges = sum(1 for c in challenges if c.get("status") == "open")
    pilot_contents = content_pilot_enabled_for_teacher()

    cols = st.columns(5 if pilot_contents else 3)

    cards = [
        (
            "🏫👥",
            "Classes et élèves",
            "Créez vos classes, importez les élèves et gérez leurs accès.",
            f"{len(classes)} classe(s) · {len(students)} élève(s)",
            "card-blue",
            "classes_students",
        ),
        (
            "🏆",
            "Défis",
            "Créez, ouvrez et gérez vos défis.",
            f"{open_challenges} défi(s) ouvert(s)",
            "card-orange",
            "challenges",
        ),
        (
            "📊",
            "Résultats",
            "Consultez les classements et les performances.",
            f"{len(results)} résultat(s)",
            "card-pink",
            "results",
        ),
    ]

    if pilot_contents:
        cards.insert(1, (
            "📚",
            "Contenus",
            "Choisissez les ressources visibles pour chacune de vos classes.",
            "Pilotage par classe",
            "card-green",
            "contents",
        ))
        cards.insert(2, (
            "👀",
            "Suivi des élèves",
            "Distinguez l'entraînement courant de la préparation aux évaluations.",
            f"{len(activity_rows)} activité(s) enregistrée(s)",
            "card-cyan",
            "tracking",
        ))

    for i, (icon, title, text_card, count, color, section) in enumerate(cards):
        with cols[i]:
            nav_card(icon, title, f"{text_card}<br><br><strong>{count}</strong>", color)

            st.button(
                f"Gérer {title.lower()}  ›",
                key=f"teacher_{section}",
                use_container_width=True,
                on_click=set_teacher_section,
                args=(section,),
            )

    st.markdown(
        '<div class="footer-note">ⓘ Toutes les données sont synchronisées avec Upstash.</div>',
        unsafe_allow_html=True,
    )



def teacher_advanced_management(scope):
    """
    Gestion avancée contextualisée.
    Chaque action concerne uniquement le professeur connecté.
    """
    configs = {
        "classes_students": {
            "title": "⚙️ Gestion avancée — Classes et élèves",
            "phrase": "SUPPRIMER CLASSES ET ELEVES",
            "button": "🗑️ Supprimer mes classes et mes élèves",
            "message": (
                "Toutes vos classes et tous vos élèves seront supprimés. "
                "Les défis et résultats déjà enregistrés sont conservés."
            ),
            "success": "Vos classes et vos élèves ont été supprimés.",
            "action": reset_classes_and_students,
        },
        "contents": {
            "title": "⚙️ Gestion avancée — Contenus",
            "phrase": "REINITIALISER LES CONTENUS",
            "button": "🗑️ Réinitialiser l'ouverture des contenus",
            "message": (
                "Tous les réglages d'ouverture ou de fermeture des contenus "
                "seront remis à zéro pour vos classes."
            ),
            "success": "Les réglages de contenus ont été réinitialisés.",
            "action": lambda: save_content_access({}),
        },
        "tracking": {
            "title": "⚙️ Gestion avancée — Suivi des élèves",
            "phrase": "SUPPRIMER LE SUIVI",
            "button": "🗑️ Supprimer mon suivi pédagogique",
            "message": (
                "Les réalisations d'exercices et les préparations d'évaluation "
                "seront supprimées. Les élèves, contenus, défis et résultats sont conservés."
            ),
            "success": "Le suivi pédagogique a été supprimé.",
            "action": reset_tracking,
        },
        "challenges": {
            "title": "⚙️ Gestion avancée — Création des défis",
            "phrase": "SUPPRIMER LES DEFIS",
            "button": "🗑️ Supprimer tous mes défis",
            "message": (
                "Vos défis seront supprimés ainsi que les équipes collaboratives associées. "
                "Les classes, élèves et résultats passés sont conservés."
            ),
            "success": "Tous vos défis ont été supprimés.",
            "action": reset_challenges,
        },
        "results": {
            "title": "⚙️ Gestion avancée — Résultats",
            "phrase": "SUPPRIMER LES RESULTATS",
            "button": "🗑️ Supprimer tous mes résultats",
            "message": (
                "Tous vos résultats enregistrés seront supprimés. "
                "Les classes, élèves et défis sont conservés."
            ),
            "success": "Tous vos résultats ont été supprimés.",
            "action": reset_results,
        },
    }

    config = configs.get(scope)
    if not config:
        return

    with st.expander(config["title"]):
        st.warning(
            "Cette zone contient des opérations irréversibles. "
            "Elles concernent uniquement votre espace professeur."
        )
        st.info(config["message"])

        confirmation = st.text_input(
            f"Pour confirmer, saisissez exactement : {config['phrase']}",
            key=f"advanced_confirm_{scope}",
        )

        if st.button(
            config["button"],
            disabled=confirmation != config["phrase"],
            use_container_width=True,
            key=f"advanced_action_{scope}",
        ):
            config["action"]()
            st.success(config["success"])
            st.rerun()


def teacher_classes_students():
    teacher_header("Classes et élèves")

    classes = get_classes()
    students = get_students()

    # -------------------------
    # Classes
    # -------------------------
    st.subheader("🏫 Mes classes")

    c1, c2 = st.columns([3, 1])

    with c1:
        class_name = st.text_input(
            "Nom de la classe",
            placeholder="Ex. 4B",
            key="class_name_input",
        )

    with c2:
        st.write("")
        st.write("")
        if st.button(
            "➕ Nouvelle classe",
            type="primary",
            use_container_width=True,
            key="create_class_button",
        ):
            if add_class(class_name):
                st.success(f"Classe {class_name.strip().upper()} créée.")
                st.rerun()
            else:
                st.warning("Cette classe existe déjà ou le nom est vide.")

    classes = get_classes()
    students = get_students()

    if classes:
        class_rows = []
        for class_item in classes:
            effectif = sum(1 for s in students if s["class_name"] == class_item)
            class_rows.append({"Classe": class_item, "Effectif": effectif})

        st.dataframe(class_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune classe enregistrée.")

    st.markdown("---")

    # -------------------------
    # Import / ajout d'élèves
    # -------------------------
    st.subheader("👥 Ajouter des élèves")

    with st.expander("📥 Importer une classe depuis Excel", expanded=not students):
        st.write(
            "Le fichier doit contenir les informations nécessaires : "
            "**Prénom**, **Initiale du nom** et **Classe**."
        )

        st.download_button(
            "📥 Télécharger le modèle Excel",
            data=student_template_xlsx_bytes(),
            file_name="modele_import_classe_ludotheque.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        uploaded_students = st.file_uploader(
            "Choisir un fichier Excel",
            type=["xlsx", "xlsm"],
            key="student_excel_upload",
        )

        if uploaded_students is not None:
            try:
                excel_df = pd.read_excel(uploaded_students)

                st.markdown("#### Aperçu")
                st.dataframe(
                    excel_df.head(15),
                    use_container_width=True,
                    hide_index=True,
                )

                first_col, initial_col, class_col = detect_student_columns(excel_df)
                detected = []

                if first_col:
                    detected.append(f"Prénom → **{first_col}**")
                if initial_col:
                    detected.append(f"Initiale → **{initial_col}**")
                if class_col:
                    detected.append(f"Classe → **{class_col}**")

                if detected:
                    st.info("Colonnes détectées : " + " · ".join(detected))

                if st.button(
                    "📥 Importer les élèves",
                    type="primary",
                    use_container_width=True,
                    key="import_students_button",
                ):
                    added, duplicates, errors = import_students_from_dataframe(excel_df)

                    if added:
                        st.success(
                            f"✅ {added} élève(s) importé(s). "
                            f"{duplicates} doublon(s) ignoré(s)."
                        )

                    if errors:
                        st.warning(f"{len(errors)} ligne(s) n'ont pas été importées.")
                        for message in errors[:20]:
                            st.write("• " + message)

                    if added:
                        st.rerun()

            except Exception as exc:
                st.error(
                    "Impossible de lire ce fichier Excel. "
                    f"Détail : {exc}"
                )

    classes = get_classes()

    if classes:
        with st.expander("➕ Ajouter ponctuellement un élève"):
            c1, c2, c3 = st.columns([2, 1, 1])

            with c1:
                first_name = st.text_input("Prénom", key="new_student_firstname")

            with c2:
                last_initial = st.text_input(
                    "Initiale",
                    max_chars=1,
                    key="new_student_initial",
                )

            with c3:
                student_class = st.selectbox(
                    "Classe",
                    classes,
                    key="new_student_class",
                )

            if st.button(
                "➕ Ajouter l'élève",
                use_container_width=True,
                key="add_single_student_button",
            ):
                student, error = add_student(first_name, last_initial, student_class)

                if error:
                    st.error(error)
                else:
                    st.success(f"Élève ajouté — code **{student['code']}**")
                    st.rerun()
    else:
        st.caption("Créez d'abord une classe avant d'ajouter un élève ponctuellement.")

    st.markdown("---")

    # -------------------------
    # Liste et accès élèves
    # -------------------------
    st.subheader("🔐 Élèves enregistrés et codes d'accès")

    students = get_students()

    if not students:
        st.info("Aucun élève enregistré.")
    else:
        filter_classes = ["Toutes"] + get_classes()
        selected_filter = st.selectbox(
            "Filtrer par classe",
            filter_classes,
            key="student_filter",
        )

        filtered = [
            s
            for s in students
            if selected_filter == "Toutes" or s["class_name"] == selected_filter
        ]

        if filtered:
            pdf_cards = generate_student_cards_pdf(filtered)
            filename = (
                "cartes_eleves_ludotheque_toutes_classes.pdf"
                if selected_filter == "Toutes"
                else f"cartes_eleves_ludotheque_{selected_filter}.pdf"
            )

            st.download_button(
                "🖨️ Télécharger les cartes élèves (QR + volet code)",
                data=pdf_cards,
                file_name=filename,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

        st.caption(
            "Les nouveaux codes comportent 6 caractères. Les anciennes fiches à 4 caractères "
            "restent valides tant que vous ne régénérez pas leur code."
        )

        # En-tête de la liste interactive.
        h1, h2, h3, h4, h5 = st.columns([2.2, 0.8, 1.0, 1.4, 1.8])
        h1.markdown("**Prénom**")
        h2.markdown("**Initiale**")
        h3.markdown("**Classe**")
        h4.markdown("**Code**")
        h5.markdown("**Accès**")

        sorted_filtered = sorted(
            filtered,
            key=lambda s: (
                s["class_name"],
                s["first_name"].lower(),
                s["last_initial"],
            ),
        )

        last_regenerated = st.session_state.get("last_regenerated_student")

        for student in sorted_filtered:
            c1, c2, c3, c4, c5 = st.columns([2.2, 0.8, 1.0, 1.4, 1.8])

            c1.write(student["first_name"])
            c2.write(student["last_initial"] + ".")
            c3.write(student["class_name"])
            c4.code(student["code"], language=None)

            if c5.button(
                "🔄 Nouveau code",
                key=f"regen_code_{student['id']}",
                use_container_width=True,
            ):
                st.session_state.pop("last_regenerated_student", None)
                regenerate_student_code_dialog(student["id"])

            if isinstance(last_regenerated, dict) and last_regenerated.get("id") == student["id"]:
                st.success(
                    f"Nouveau code créé pour **{last_regenerated['first_name']} "
                    f"{last_regenerated['last_initial']}.** : **{last_regenerated['new_code']}**. "
                    "L'ancienne carte est désormais invalide."
                )

                # Récupère la fiche mise à jour afin de générer uniquement la nouvelle carte
                # de l'élève concerné, avec son nouveau code et son nouveau QR.
                refreshed_students = get_students()
                refreshed_student = next(
                    (s for s in refreshed_students if s.get("id") == student["id"]),
                    None,
                )

                if refreshed_student:
                    single_card_pdf = generate_student_cards_pdf([refreshed_student])
                    safe_first_name = re.sub(
                        r"[^A-Za-z0-9_-]+",
                        "_",
                        refreshed_student["first_name"],
                    ).strip("_") or "eleve"
                    safe_class_name = re.sub(
                        r"[^A-Za-z0-9_-]+",
                        "_",
                        refreshed_student["class_name"],
                    ).strip("_") or "classe"

                    st.download_button(
                        f"🖨️ Télécharger la nouvelle carte de {refreshed_student['first_name']} "
                        f"{refreshed_student['last_initial']}.",
                        data=single_card_pdf,
                        file_name=(
                            f"carte_ludotheque_{safe_first_name}_"
                            f"{refreshed_student['last_initial']}_{safe_class_name}.pdf"
                        ),
                        mime="application/pdf",
                        type="primary",
                        use_container_width=False,
                        key=f"download_new_card_{student['id']}_{last_regenerated['new_code']}",
                    )

                st.caption(
                    "Vous pouvez aussi retélécharger les cartes de toute la classe avec le bouton bleu situé au-dessus."
                )
                st.session_state.pop("last_regenerated_student", None)

    st.markdown("---")

    # -------------------------
    # Suppressions
    # -------------------------
    st.subheader("🗑️ Retirer un élève ou supprimer une classe")

    students = get_students()
    classes = get_classes()

    tab_student, tab_class = st.tabs(["Retirer un élève", "Supprimer une classe"])

    with tab_student:
        if students:
            student_options = {
                f"{s['first_name']} {s['last_initial']}. — {s['class_name']} — {s['code']}": s["id"]
                for s in sorted(
                    students,
                    key=lambda s: (
                        s["class_name"],
                        s["first_name"].lower(),
                        s["last_initial"],
                    ),
                )
            }

            selected_student_label = st.selectbox(
                "Élève à retirer",
                list(student_options.keys()),
                key="student_to_delete",
            )

            confirm_student = st.checkbox(
                "Je confirme le retrait de cet élève de la base.",
                key="confirm_delete_student",
            )

            if st.button(
                "🗑️ Retirer cet élève",
                disabled=not confirm_student,
                use_container_width=True,
                key="delete_student_button",
            ):
                if delete_student(student_options[selected_student_label]):
                    st.success("Élève retiré de la base.")
                    st.rerun()
                else:
                    st.error("Élève introuvable.")
        else:
            st.info("Aucun élève enregistré.")

    with tab_class:
        if classes:
            class_to_delete = st.selectbox(
                "Classe à supprimer",
                classes,
                key="class_to_delete",
            )

            effectif_to_delete = sum(
                1 for s in students if s["class_name"] == class_to_delete
            )

            if effectif_to_delete:
                st.warning(
                    f"La classe {class_to_delete} contient encore "
                    f"{effectif_to_delete} élève(s). "
                    "Supprimez ou déplacez d'abord ces élèves."
                )
            else:
                confirm_class = st.checkbox(
                    f"Je confirme la suppression de la classe {class_to_delete}.",
                    key="confirm_delete_class",
                )

                if st.button(
                    "🗑️ Supprimer cette classe",
                    disabled=not confirm_class,
                    use_container_width=True,
                    key="delete_class_button",
                ):
                    ok, error = delete_class(class_to_delete)

                    if ok:
                        st.success(f"Classe {class_to_delete} supprimée.")
                        st.rerun()
                    else:
                        st.error(error or "Suppression impossible.")
        else:
            st.info("Aucune classe enregistrée.")


    teacher_advanced_management("classes_students")

def teacher_contents():
    teacher_header("Contenus")

    if not content_pilot_enabled_for_teacher():
        st.info("Le pilotage des contenus n’est pas encore activé pour ce compte professeur.")
        return

    classes = get_classes()
    if not classes:
        st.info("Créez d'abord une classe dans « Classes et élèves ».")
        return

    st.markdown(
        '<div class="section-title">📚 Contenus disponibles par classe</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Les contenus suivent la progression de 4e. Chaque ressource reste indépendante : "
        "vous pouvez ouvrir ou fermer un exercice ou un jeu sans ouvrir tout le chapitre. "
        "Les ressources fermées restent invisibles pour les élèves."
    )

    selected_class = st.selectbox(
        "Classe à configurer",
        classes,
        key="content_class_select",
    )
    access = get_content_access()
    class_access = dict(access.get(selected_class, {}))

    # Migration douce des anciens interrupteurs du prototype.
    if "atoms_molecules" in class_access and "domino_molecules" not in class_access:
        class_access["domino_molecules"] = bool(class_access.get("atoms_molecules"))
    if "states_matter" in class_access and "exercise_states_matter" not in class_access:
        class_access["exercise_states_matter"] = bool(class_access.get("states_matter"))

    changed = False

    for chapter in PROGRESSION_CHAPTERS:
        resources = [
            (content_id, info)
            for content_id, info in PILOT_CONTENTS.items()
            if info.get("chapter") == chapter
        ]
        resources.sort(key=lambda item: item[1].get("order", 999))

        opened_count = sum(
            1
            for content_id, _ in resources
            if bool(class_access.get(content_id, False))
        )
        total_count = len(resources)

        if chapter == "Autres contenus déjà prêts":
            title = f"🧰 {chapter} — {opened_count}/{total_count} ouvert(s)"
        else:
            title = f"{chapter} — {opened_count}/{total_count} ouvert(s)"

        with st.expander(title, expanded=(chapter == "Chapitre 1 — Organisation de la matière")):
            if not resources:
                st.caption(
                    "Aucune ressource n'est encore ajoutée dans ce chapitre. "
                    "Les futurs exercices seront classés ici au fur et à mesure."
                )
                continue

            for content_id, info in resources:
                c1, c2 = st.columns([4.8, 1.2])

                with c1:
                    st.markdown(f"**{info['label']}**")
                    st.caption(info["description"])

                with c2:
                    old_value = bool(class_access.get(content_id, False))
                    value = st.toggle(
                        "Visible",
                        value=old_value,
                        key=f"content_toggle_{selected_class}_{content_id}",
                        help="Affiche ou masque uniquement cette ressource pour la classe.",
                    )

                    if value != old_value:
                        class_access[content_id] = value
                        changed = True

    if changed:
        access[selected_class] = class_access
        save_content_access(access)
        st.success(f"Accès de la classe {selected_class} mis à jour.")
        st.rerun()

    opened = [
        info["label"]
        for content_id, info in PILOT_CONTENTS.items()
        if class_access.get(content_id)
    ]

    st.markdown("---")
    if opened:
        st.info(
            "Actuellement visible pour cette classe : "
            + ", ".join(opened)
        )
    else:
        st.info("Aucun contenu n'est actuellement ouvert pour cette classe.")

    teacher_advanced_management("contents")

def teacher_challenges():
    teacher_header("Défis")

    classes = get_classes()

    st.subheader("Créer un nouveau défi")

    if not classes:
        st.warning("Créez d'abord au moins une classe.")
    else:
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        with c1:
            selected_class = st.selectbox(
                "Classe",
                classes,
                key="challenge_class",
            )

        with c2:
            activity = st.selectbox(
                "Activité",
                ["Dominos"],
                key="challenge_activity",
            )

        with c3:
            theme = st.selectbox(
                "Thème",
                ["Molécules", "Verrerie", "Ions", "Électricité"],
                key="challenge_theme",
            )

        with c4:
            challenge_level = st.selectbox(
                "Niveau",
                levels_for_theme(theme),
                key="challenge_level",
                format_func=lambda x: f"{LEVELS[x]['emoji']} {x}",
            )

        with c5:
            max_attempts = st.selectbox(
                "Tentatives",
                [1, 2, 3],
                index=0,
            )

        with c6:
            duration_minutes = st.number_input(
                "Durée (min)",
                min_value=5,
                max_value=480,
                value=55,
                step=5,
                key="challenge_duration",
            )

            no_time_limit = st.checkbox(
                "♾️ Sans limite de temps",
                value=False,
                key="challenge_no_time_limit",
            )

        mode_col, size_col, mode_spacer = st.columns([2, 2, 8])

        with mode_col:
            challenge_mode = st.selectbox(
                "Mode",
                ["Individuel", "Collaboratif"],
                key="challenge_mode",
                format_func=lambda x: (
                    "👤 Individuel"
                    if x == "Individuel"
                    else "👥 Collaboratif"
                ),
            )

        with size_col:
            team_size = st.selectbox(
                "Élèves par équipe",
                [2, 3, 4],
                index=2,
                key="challenge_team_size",
                disabled=challenge_mode != "Collaboratif",
            )

        if st.button(
            "🏆 Créer le défi",
            type="primary",
            use_container_width=True,
        ):
            challenge = create_challenge(
                selected_class,
                activity,
                theme,
                challenge_level,
                max_attempts,
                duration_minutes=duration_minutes,
                no_time_limit=no_time_limit,
                mode=challenge_mode,
                team_size=team_size,
            )

            if challenge.get("duration_minutes") is None:
                timing_text = "sans limite de temps"
            else:
                timing_text = f"pour {challenge['duration_minutes']} min"

            mode_text = (
                "collaboratif"
                if challenge.get("mode") == "Collaboratif"
                else "individuel"
            )

            st.success(
                f"Défi **{mode_text}** créé — code **{challenge['code']}** "
                f"pour **{challenge['class_name']}**, {timing_text}."
            )
            st.rerun()

    st.markdown("---")
    st.subheader("Défis enregistrés")

    challenges = get_challenges()

    if not challenges:
        st.info("Aucun défi enregistré.")
        return

    for challenge in reversed(challenges):
        status_open = challenge.get("status") == "open"
        remaining = challenge_remaining_seconds(challenge)

        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([1, 1.35, 1.7, 1, 1.5, 1])

            with c1:
                st.markdown(f"### {challenge['code']}")

                if status_open:
                    st.write("🟢 Ouvert")
                elif challenge.get("closed_reason") == "expired":
                    st.write("⏱️ Terminé")
                else:
                    st.write("⚫ Fermé")

            with c2:
                st.write(f"**Classe :** {challenge['class_name']}")
                st.write(f"**Niveau :** {challenge['level']}")

            with c3:
                st.write(
                    f"**Activité :** {challenge.get('activity', 'Dominos')}"
                )
                st.write(
                    f"**Thème :** {challenge.get('theme', 'Molécules')}"
                )

            with c4:
                mode = challenge.get("mode", "Individuel")
                st.write(f"**Mode :** {mode}")

                if mode == "Collaboratif":
                    st.write(
                        f"**Équipe :** {challenge.get('team_size', 4)} élèves"
                    )
                else:
                    st.write(
                        f"**Tentatives :** {challenge['max_attempts']}"
                    )

            with c5:
                duration = challenge.get("duration_minutes")

                if duration is None:
                    st.write("**Durée :** Sans limite")
                else:
                    st.write(f"**Durée :** {duration} min")

                if status_open:
                    st.write(
                        f"**Restant :** {format_remaining_time(remaining)}"
                    )

            with c6:
                if status_open:
                    if st.button(
                        "Fermer",
                        key=f"close_{challenge['code']}",
                        use_container_width=True,
                    ):
                        close_challenge(challenge["code"])
                        st.rerun()

    collaborative_open = [
        c for c in challenges
        if c.get("status") == "open"
        and c.get("mode") == "Collaboratif"
    ]

    if collaborative_open:
        st.markdown("---")
        st.subheader("👥 Équipes collaboratives en cours")

        for challenge in collaborative_open:
            teams = get_collab_teams(
                st.session_state["teacher_id"],
                challenge["code"],
            )

            if not teams:
                st.caption(
                    f"Défi {challenge['code']} : aucune équipe créée pour le moment."
                )
                continue

            rows = []
            for team_code, team in teams.items():
                game = team.get("game") or {}
                departures = team.get("departures", [])
                departed_names = ", ".join(
                    f"{d['first_name']} {d['last_initial']}."
                    for d in departures
                )

                rows.append(
                    {
                        "Défi": challenge["code"],
                        "Équipe": team_code,
                        "Élèves présents": len(team.get("members", [])),
                        "Attendus au départ": team.get(
                            "target_size",
                            challenge.get("team_size", 4),
                        ),
                        "État": team.get("status", "lobby"),
                        "Élèves ayant quitté": departed_names or "—",
                        "Dominos": len(game.get("chain", [])) if game else 0,
                        "Erreurs": game.get("errors", 0) if game else 0,
                    }
                )

            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)



    teacher_advanced_management("challenges")

def teacher_tracking():
    teacher_header("Suivi des élèves")

    if not content_pilot_enabled_for_teacher():
        st.info("Le suivi pédagogique n’est pas encore activé pour ce compte professeur.")
        return

    st.markdown(
        '<div class="section-title">👀 Suivi des élèves</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Ce tableau sert au suivi pédagogique de la Ludothèque. "
        "Il distingue l'entraînement libre de la préparation volontaire d'une évaluation."
    )

    training_tab, evaluation_tab = st.tabs([
        "📚 Entraînement",
        "🎯 Préparation des évaluations",
    ])

    students = get_students()
    rows = get_activity_log()

    with training_tab:
        st.markdown("### Entraînement courant")

        c1, c2, c3 = st.columns(3)
        with c1:
            class_filter = st.selectbox(
                "Classe",
                ["Toutes"] + get_classes(),
                key="tracking_class_filter",
            )

        chapters = [
            chapter for chapter in PROGRESSION_CHAPTERS
            if chapter != "Autres contenus déjà prêts"
        ]
        with c2:
            chapter_filter = st.selectbox(
                "Chapitre",
                ["Tous"] + chapters,
                key="tracking_chapter_filter",
            )

        exercise_options = {
            info["label"]: content_id
            for content_id, info in PILOT_CONTENTS.items()
            if content_id in tracked_exercise_ids()
        }
        with c3:
            exercise_label = st.selectbox(
                "Exercice",
                ["Tous"] + list(exercise_options.keys()),
                key="tracking_exercise_filter",
            )

        filtered_rows = [
            row for row in rows
            if row.get("activity_kind") == "training"
            and (class_filter == "Toutes" or row.get("class_name") == class_filter)
            and (
                chapter_filter == "Tous"
                or row.get("chapter") == chapter_filter
            )
            and (
                exercise_label == "Tous"
                or row.get("resource_id") == exercise_options.get(exercise_label)
            )
        ]

        latest = latest_training_by_student_resource(filtered_rows)
        attempt_counts, restart_counts = training_attempt_counts(filtered_rows)

        selected_students = [
            s for s in students
            if class_filter == "Toutes" or s.get("class_name") == class_filter
        ]

        if exercise_label != "Tous":
            resource_ids = [exercise_options[exercise_label]]
        elif chapter_filter != "Tous":
            resource_ids = [
                cid for cid in tracked_exercise_ids()
                if PILOT_CONTENTS.get(cid, {}).get("chapter") == chapter_filter
            ]
        else:
            resource_ids = tracked_exercise_ids()

        table = []
        for student in sorted(
            selected_students,
            key=lambda s: (s.get("class_name", ""), s.get("first_name", "").lower()),
        ):
            latest_rows = [
                latest[(student.get("id"), rid)]
                for rid in resource_ids
                if (student.get("id"), rid) in latest
            ]

            completed_rows = [
                r for r in filtered_rows
                if r.get("student_id") == student.get("id")
                and r.get("resource_id") in resource_ids
                and r.get("status", "completed") == "completed"
            ]

            done_resources = {
                r.get("resource_id") for r in completed_rows
            }

            if latest_rows or completed_rows:
                valid_scores = []
                for row in completed_rows:
                    try:
                        valid_scores.append(float(row.get("score_percent")))
                    except (TypeError, ValueError):
                        pass
                best = max(valid_scores) if valid_scores else None
                done = len(done_resources)
                last_activity = max(
                    [str(r.get("finished_at", "")) for r in latest_rows + completed_rows]
                )
                attempts = sum(
                    attempt_counts.get((student.get("id"), rid), 0)
                    for rid in resource_ids
                )
                restarts = sum(
                    restart_counts.get((student.get("id"), rid), 0)
                    for rid in resource_ids
                )

                if done == len(resource_ids) and resource_ids:
                    status = "✅ Actif"
                elif attempts > 0:
                    status = "🟠 En cours"
                else:
                    status = "⚪ Non commencé"

                result_text = f"{best} %" if best is not None else "—"
            else:
                done = 0
                attempts = 0
                restarts = 0
                last_activity = ""
                status = "⚪ Non commencé"
                result_text = "—"

            table.append({
                "Élève": f"{student.get('first_name', '')} {student.get('last_initial', '')}.",
                "Classe": student.get("class_name", ""),
                "Activité": status,
                "Exercices faits": f"{done}/{len(resource_ids)}" if resource_ids else "—",
                "Résultat": result_text,
                "Tentatives": attempts if attempts else "—",
                "Recommencées": restarts if restarts else "—",
                "Dernière activité": format_short_datetime(last_activity),
                "Dernière connexion": format_short_datetime(student.get("last_login_at")),
            })

        if table:
            st.dataframe(table, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun élève ne correspond à ces filtres.")

    with evaluation_tab:
        st.markdown("### Préparation des évaluations")
        st.caption(
            "Le professeur choisit les exercices qui constituent la préparation. "
            "La Ludothèque indique ensuite l'avancement et une éventuelle éligibilité au bonus ; "
            "le professeur reste seul décisionnaire."
        )

        with st.expander("➕ Créer une préparation d'évaluation"):
            prep_class = st.selectbox(
                "Classe",
                get_classes(),
                key="prep_class",
            )

            prep_chapter = st.selectbox(
                "Chapitre",
                [
                    chapter for chapter in PROGRESSION_CHAPTERS
                    if chapter != "Autres contenus déjà prêts"
                ],
                key="prep_chapter",
            )

            eligible = {
                info["label"]: cid
                for cid, info in PILOT_CONTENTS.items()
                if cid in tracked_exercise_ids()
                and info.get("chapter") == prep_chapter
            }

            prep_name = st.text_input(
                "Nom de la préparation",
                placeholder="Ex. Évaluation — Chapitre 1",
                key="prep_name",
            )

            selected_labels = st.multiselect(
                "Exercices à refaire",
                list(eligible.keys()),
                key="prep_exercises",
            )

            threshold = st.slider(
                "Seuil indicatif pour « +1 possible »",
                min_value=50,
                max_value=100,
                value=80,
                step=5,
                key="prep_threshold",
            )

            if st.button(
                "Créer la préparation",
                type="primary",
                use_container_width=True,
                disabled=not prep_name.strip() or not selected_labels,
            ):
                preparations = get_evaluation_preparations()
                preparations.append({
                    "id": secrets.token_urlsafe(10),
                    "name": prep_name.strip(),
                    "class_name": prep_class,
                    "chapter": prep_chapter,
                    "resource_ids": [eligible[label] for label in selected_labels],
                    "threshold": int(threshold),
                    "active": True,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                })
                save_evaluation_preparations(preparations)
                st.success("Préparation créée.")
                st.rerun()

        preparations = get_evaluation_preparations()
        if not preparations:
            st.info("Aucune préparation d'évaluation n'est encore créée.")
        else:
            prep_labels = {
                f"{p['name']} — {p['class_name']}": p["id"]
                for p in preparations
            }
            selected_prep_label = st.selectbox(
                "Préparation à consulter",
                list(prep_labels.keys()),
                key="prep_tracking_select",
            )
            prep = next(
                p for p in preparations
                if p["id"] == prep_labels[selected_prep_label]
            )

            target_students = [
                s for s in students
                if s.get("class_name") == prep.get("class_name")
            ]
            # Pour une préparation d'évaluation, seuls les exercices réellement
            # terminés doivent compter. Une ligne "restarted" peut avoir
            # score_percent = None : elle ne doit donc ni être considérée comme
            # un exercice fait, ni entrer dans le calcul de la moyenne.
            # Une préparation d'évaluation constitue un nouveau point de départ :
            # seules les tentatives terminées APRÈS sa création doivent compter.
            prep_created_at = str(prep.get("created_at", "") or "")

            completed_training_rows = [
                row for row in rows
                if row.get("activity_kind") == "training"
                and row.get("status", "completed") == "completed"
                and row.get("score_percent") is not None
                and (
                    not prep_created_at
                    or str(row.get("finished_at", "") or "") >= prep_created_at
                )
            ]
            latest_all = latest_training_by_student_resource(completed_training_rows)

            required = prep.get("resource_ids", [])
            threshold = int(prep.get("threshold", 80))

            prep_table = []
            for student in sorted(
                target_students,
                key=lambda s: s.get("first_name", "").lower(),
            ):
                done_rows = [
                    latest_all[(student.get("id"), rid)]
                    for rid in required
                    if (student.get("id"), rid) in latest_all
                ]
                done = len(done_rows)
                total = len(required)

                if done == 0:
                    status = "❌ Non commencée"
                    result = "—"
                    bonus = "—"
                else:
                    numeric_scores = []
                    for row in done_rows:
                        try:
                            numeric_scores.append(float(row.get("score_percent")))
                        except (TypeError, ValueError):
                            pass

                    if numeric_scores:
                        average = round(sum(numeric_scores) / len(numeric_scores))
                        result = f"{average} %"
                    else:
                        average = None
                        result = "—"
                    if done == total:
                        status = "✅ Terminée"
                        bonus = (
                            "+1 possible"
                            if average is not None and average >= threshold
                            else "—"
                        )
                    else:
                        status = "🟠 Partielle"
                        bonus = "—"

                prep_table.append({
                    "Élève": f"{student.get('first_name', '')} {student.get('last_initial', '')}.",
                    "Préparation": status,
                    "Exercices faits": f"{done}/{total}",
                    "Résultat": result,
                    "Bonus": bonus,
                })

            st.markdown(
                f"**{prep['name']}** · {prep['chapter']} · "
                f"seuil indicatif : **{threshold} %**"
            )

            if prep_created_at:
                st.caption(
                    "Seules les tentatives réalisées depuis la création de cette "
                    "préparation sont prises en compte."
                )
            st.dataframe(
                prep_table,
                use_container_width=True,
                hide_index=True,
            )

            # ------------------------------------------------------------
            # Export CSV de la préparation sélectionnée
            # ------------------------------------------------------------
            export_rows = []
            for row in prep_table:
                export_rows.append({
                    "Préparation": prep.get("name", ""),
                    "Classe": prep.get("class_name", ""),
                    "Chapitre": prep.get("chapter", ""),
                    "Seuil bonus (%)": threshold,
                    "Date de création": format_short_datetime(prep.get("created_at")),
                    "Élève": row.get("Élève", ""),
                    "État de la préparation": row.get("Préparation", ""),
                    "Exercices faits": row.get("Exercices faits", ""),
                    "Résultat": row.get("Résultat", ""),
                    "Bonus": row.get("Bonus", ""),
                })

            export_df = pd.DataFrame(export_rows)
            csv_bytes = export_df.to_csv(
                index=False,
                sep=";",
            ).encode("utf-8-sig")

            safe_prep_name = re.sub(
                r"[^A-Za-z0-9_-]+",
                "_",
                str(prep.get("name", "preparation")).strip(),
            ).strip("_") or "preparation"

            safe_class_name = re.sub(
                r"[^A-Za-z0-9_-]+",
                "_",
                str(prep.get("class_name", "classe")).strip(),
            ).strip("_") or "classe"

            action_export, action_delete = st.columns(2, gap="large")

            with action_export:
                st.download_button(
                    "📥 Exporter le tableau",
                    data=csv_bytes,
                    file_name=f"{safe_prep_name}_{safe_class_name}_resultats.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"download_prep_{prep.get('id', 'current')}",
                )

            # ------------------------------------------------------------
            # Suppression protégée de la préparation
            # ------------------------------------------------------------
            prep_id = prep.get("id")
            confirm_key = f"confirm_delete_prep_{prep_id}"

            with action_delete:
                with st.expander("🗑️ Supprimer la préparation"):
                    st.warning(
                        "Cette action supprime uniquement cette préparation. "
                        "Les résultats et l'historique d'entraînement des élèves "
                        "sont conservés."
                    )
                    confirmed = st.checkbox(
                        "Je confirme la suppression de cette préparation.",
                        key=confirm_key,
                    )

                    if st.button(
                        "Supprimer définitivement",
                        key=f"delete_prep_{prep_id}",
                        use_container_width=True,
                        disabled=not confirmed,
                    ):
                        updated_preparations = [
                            item for item in preparations
                            if item.get("id") != prep_id
                        ]
                        save_evaluation_preparations(updated_preparations)

                        # Nettoyer la sélection devenue invalide avant rerun.
                        st.session_state.pop("prep_tracking_select", None)
                        st.session_state.pop(confirm_key, None)

                        st.success("Préparation supprimée.")
                        st.rerun()


    teacher_advanced_management("tracking")

def teacher_results():
    teacher_header("Résultats")

    results = get_results()

    st.subheader("Résultats enregistrés")

    if not results:
        st.info("Aucun résultat pour le moment.")
        return

    c1, c2 = st.columns(2)

    with c1:
        result_class = st.selectbox(
            "Classe",
            ["Toutes"] + get_classes(),
            key="result_class_filter",
        )

    with c2:
        challenge_codes = ["Tous"] + sorted(
            {str(r["challenge_code"]) for r in results},
            reverse=True,
        )

        result_challenge = st.selectbox(
            "Défi",
            challenge_codes,
            key="result_challenge_filter",
        )

    filtered = [
        r
        for r in results
        if (
            (result_class == "Toutes" or r["class_name"] == result_class)
            and (
                result_challenge == "Tous"
                or str(r["challenge_code"]) == result_challenge
            )
        )
    ]

    filtered = sorted(
        filtered,
        key=lambda r: (
            r["errors"],
            r["time_seconds"],
        ),
    )

    table = []

    for rank, r in enumerate(filtered, start=1):
        if r.get("result_type") == "team":
            members_text = ", ".join(
                f"{m['first_name']} {m['last_initial']}."
                for m in r.get("team_members", [])
            )
            departed_text = ", ".join(
                f"{d['first_name']} {d['last_initial']}."
                for d in r.get("team_departures", [])
            )
            participant = f"Équipe {r.get('team_code', '')}"
            mode = "👥 Collaboratif"
        else:
            members_text = ""
            departed_text = ""
            participant = f"{r['first_name']} {r['last_initial']}."
            mode = "👤 Individuel"

        table.append(
            {
                "Rang": rank,
                "Participant": participant,
                "Membres à la fin": members_text,
                "Ont quitté": departed_text,
                "Mode": mode,
                "Classe": r["class_name"],
                "Défi": r["challenge_code"],
                "Activité": r.get("activity", "Dominos"),
                "Thème": r.get("theme", "Molécules"),
                "Niveau": r["level"],
                "Erreurs": r["errors"],
                "Détail erreurs": (
                    ", ".join(
                        f"{detail.get('first_name', '')} {detail.get('last_initial', '')}."
                        for detail in r.get("error_details", [])
                    )
                    if r.get("result_type") == "team" and r.get("error_details")
                    else ""
                ),
                "Temps": f"{r['time_seconds'] // 60}:{r['time_seconds'] % 60:02d}",
                "Tentative": r.get("attempt", 1),
                "Badge": "🎯 Sans faute" if r["errors"] == 0 else "",
            }
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


    teacher_advanced_management("results")

def page_teacher():
    if not teacher_login():
        return

    # Réduction de l'espace blanc supérieur dans l'espace professeur uniquement.
    st.markdown(
        """
        <style>
        .stMainBlockContainer,
        [data-testid="stMainBlockContainer"],
        .block-container {
            padding-top: 0.2rem !important;
            margin-top: 0 !important;
        }

        /* Rapproche le premier contenu du haut sans toucher à la partie élève. */
        [data-testid="stMainBlockContainer"] > div:first-child {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Dans la V65, .block-container est limité à 1500 px et centré.
    # Sur un grand écran cela crée une large bande vide à gauche et à droite.
    # Pour l'espace professeur uniquement, on utilise toute la largeur utile.
    st.markdown(
        """
        <style>
        .stMainBlockContainer,
        [data-testid="stMainBlockContainer"],
        .block-container {
            max-width: none !important;
            width: 100% !important;
            padding-left: 0.7rem !important;
            padding-right: 0.9rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    section = st.session_state.get(
        "teacher_section",
        "dashboard",
    )

    # Vrai bandeau gauche dans la mise en page principale.
    with st.container(key="teacher_page_shell"):
        left_col, main_col = st.columns(
            [1.18, 7.82],
            gap="medium",
            vertical_alignment="top",
        )

        with left_col:
            teacher_left_panel(section)

        with main_col:
            if section == "dashboard":
                teacher_dashboard()
            elif section in ("classes_students", "classes", "students"):
                teacher_classes_students()
            elif section == "contents":
                teacher_contents()
            elif section == "tracking":
                teacher_tracking()
            elif section == "challenges":
                teacher_challenges()
            elif section == "results":
                teacher_results()



def page_entry_gate():
    """Identification générale : élève par code/QR, professeur par compte sécurisé."""
    image_path = Path("assets/accueil_ludotheque.png")

    if not image_path.exists():
        st.error("L'image d'accueil est introuvable dans assets/accueil_ludotheque.png.")
        return

    # Un QR élève permet d'ouvrir directement sa session.
    qr_student_code = st.query_params.get("student_code")
    if qr_student_code:
        student = find_student_by_code(str(qr_student_code))
        if student:
            register_student_login(student)
            st.session_state.app_authenticated = True
            st.session_state.app_user_type = "student"
            st.session_state.app_student = student
            st.session_state.challenge_student = student
            request_page_transition()
            st.session_state.page = "home"
            st.query_params.clear()
            st.rerun()

    # Compatibilité temporaire avec les anciennes cartes QR fondées sur l'ID.
    legacy_student_id = st.query_params.get("student")
    if legacy_student_id:
        student = find_student_by_id(str(legacy_student_id))
        if student and not student.get("code_regenerated_at"):
            register_student_login(student)
            st.session_state.app_authenticated = True
            st.session_state.app_user_type = "student"
            st.session_state.app_student = student
            st.session_state.challenge_student = student
            request_page_transition()
            st.session_state.page = "home"
            st.query_params.clear()
            st.rerun()

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1480px !important;
            padding-top: 0.55rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }

        .st-key-entry_gate_image {
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        .st-key-entry_gate_image div[data-testid="stImage"] {
            width: 100% !important;
            margin: 0 !important;
        }

        .st-key-entry_gate_image div[data-testid="stImage"] img {
            width: 100% !important;
            height: auto !important;
            display: block !important;
            margin: 0 !important;
            border-radius: 10px !important;
        }

        .st-key-entry_gate_card {
            width: 100% !important;
            max-width: 420px !important;
            margin: 0 !important;
            padding: 22px 20px 20px 20px !important;
            border-radius: 22px !important;
            background: rgba(255,255,255,0.985) !important;
            border: 1px solid #e3eaf5 !important;
            box-shadow: 0 14px 34px rgba(21,49,96,0.16) !important;
        }

        .entry-title {
            text-align:center;
            font-size:1.08rem;
            font-weight:850;
            color:#153160;
            margin:0 0 12px 0;
        }

        .entry-hint {
            text-align:center;
            font-size:.82rem;
            color:#52647d;
            margin:0 0 12px 0;
            line-height:1.35;
        }

        .st-key-entry_gate_card input {
            text-align: center !important;
        }

        .st-key-entry_gate_card div[data-testid="stButton"] > button {
            min-height: 2.7rem !important;
            border-radius: 12px !important;
            box-shadow: none !important;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-left: .65rem !important;
                padding-right: .65rem !important;
            }
            .st-key-entry_gate_card {
                width: 100% !important;
                max-width: none !important;
                margin-top: .8rem !important;
                padding: 1rem .9rem 1.1rem .9rem !important;
            }
            .st-key-entry_gate_card .entry-title {
                font-size: 1.15rem !important;
                margin-bottom: .8rem !important;
            }
            .st-key-entry_gate_card .entry-hint {
                font-size: .94rem !important;
                margin-top: .7rem !important;
                margin-bottom: .8rem !important;
            }
            .st-key-entry_gate_card div[data-testid="stButton"] > button {
                min-height: 3.25rem !important;
                font-size: 1rem !important;
                padding-left: .6rem !important;
                padding-right: .6rem !important;
            }
            .st-key-entry_gate_card input {
                min-height: 3.15rem !important;
                font-size: 1.05rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Sur ordinateur : image à gauche, identification à droite.
    # Sur écran étroit, Streamlit empile naturellement les colonnes.
    # Deux colonnes réellement distinctes : visuel à gauche, connexion à droite.
    image_col, login_col = st.columns([7, 3], gap="medium", vertical_alignment="center")

    with image_col:
        with st.container(key="entry_gate_image"):
            st.image(str(image_path), use_container_width=True)

    with login_col:
        with st.container(key="entry_gate_card"):
            st.markdown(
                '<div class="entry-title">Identifie-toi pour entrer</div>',
                unsafe_allow_html=True,
            )

            # Choix de rôle volontairement présenté sous forme de gros boutons.
            # C'est beaucoup plus lisible sur téléphone que les petits boutons radio.
            if "entry_user_type" not in st.session_state:
                st.session_state.entry_user_type = "Élève"

            role_left, role_right = st.columns(2, gap="small")
            with role_left:
                if st.button(
                    "🎓  Élève",
                    key="entry_role_student",
                    type="primary" if st.session_state.entry_user_type == "Élève" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.entry_user_type = "Élève"
                    st.rerun()

            with role_right:
                if st.button(
                    "👩‍🏫  Professeur",
                    key="entry_role_teacher",
                    type="primary" if st.session_state.entry_user_type == "Professeur" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.entry_user_type = "Professeur"
                    st.rerun()

            user_type = st.session_state.entry_user_type

            if user_type == "Élève":
                st.markdown(
                    '<div class="entry-hint">Entre ton code personnel ou utilise le QR de ta carte.</div>',
                    unsafe_allow_html=True,
                )

                entered_code = st.text_input(
                    "Code personnel",
                    key="entry_student_code",
                    placeholder="Ex. K7P4QM",
                    max_chars=6,
                    label_visibility="collapsed",
                )

                if st.button(
                    "Entrer dans ma Ludothèque",
                    type="primary",
                    use_container_width=True,
                    key="entry_student_button",
                ):
                    student = find_student_by_code(entered_code)

                    if student:
                        register_student_login(student)
                        st.session_state.app_authenticated = True
                        st.session_state.app_user_type = "student"
                        st.session_state.app_student = student
                        st.session_state.challenge_student = student
                        request_page_transition()
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error("Code personnel inconnu.")

            else:
                st.markdown(
                    '<div class="entry-hint">Connexion à l’espace professeur sécurisé.</div>',
                    unsafe_allow_html=True,
                )

                accounts = get_teacher_accounts()
                if not accounts:
                    st.error("Aucun compte professeur n'est configuré dans les Secrets Streamlit.")
                    return

                teacher_ids = list(accounts.keys())
                selected_id = st.selectbox(
                    "Professeur",
                    teacher_ids,
                    format_func=lambda tid: accounts[tid]["name"],
                    key="entry_teacher_account",
                )
                password = st.text_input(
                    "Mot de passe",
                    type="password",
                    key="entry_teacher_password",
                )

                if st.button(
                    "Entrer comme professeur",
                    type="primary",
                    use_container_width=True,
                    key="entry_teacher_button",
                ):
                    if secrets.compare_digest(password, accounts[selected_id]["password"]):
                        st.session_state.teacher_authenticated = True
                        st.session_state.teacher_id = selected_id
                        st.session_state.teacher_name = accounts[selected_id]["name"]
                        st.session_state.teacher_section = "dashboard"
                        st.session_state.app_authenticated = True
                        st.session_state.app_user_type = "teacher"
                        st.session_state.pop("app_student", None)
                        st.session_state.pop("challenge_student", None)
                        request_page_transition()
                        st.session_state.page = "home"
                        st.rerun()
                    else:
                        st.error("Mot de passe incorrect.")


# ============================================================
# ROUTEUR PRINCIPAL
# ============================================================

# Identification générale : aucun contenu n'est accessible avant reconnaissance.
if not st.session_state.get("app_authenticated", False):
    page_entry_gate()
    st.stop()

if "page" not in st.session_state:
    st.session_state.page = "home"

page = st.session_state.page

# Règle unique : toute navigation passe par le même voile de transition.
render_page_transition()

if page == "home":
    page_home()
elif page == "free_activity":
    page_free_activity()
elif page == "exercise_topics":
    page_exercise_topics()
elif page == "exercise1_states_water":
    page_exercise1_states_water()
elif page == "exercise2_water_properties":
    page_exercise2_water_properties()
elif page == "exercise3_particle_models":
    page_exercise3_particle_models()
elif page == "exercise4_oxygen_bottle":
    page_exercise4_oxygen_bottle()
elif page == "exercise5_seawater_mixture":
    page_exercise5_seawater_mixture()
elif page == "exercise6_water_alcohol_volume":
    page_exercise6_water_alcohol_volume()
elif page == "exercise7_solid_mixtures_alloys":
    page_exercise7_solid_mixtures_alloys()
elif page == "exercise8_element_symbols":
    page_exercise8_element_symbols()
elif page == "exercise9_atom_or_molecule":
    page_exercise9_atom_or_molecule()
elif page == "exercise10_ethanol":
    page_exercise10_ethanol()
elif page == "exercise11_nitrous_oxide":
    page_exercise11_nitrous_oxide()
elif page == "exercise12_caffeine":
    page_exercise12_caffeine()
elif page == "exercise13_names_formulas":
    page_exercise13_names_formulas()
elif page == "exercise14_molecule_formulas":
    page_exercise14_molecule_formulas()
elif page == "exercise_states_matter":
    page_states_matter_training()
elif page == "free_theme":
    page_free_theme()
elif page == "free_level":
    page_free_level()
elif page == "free_game":
    page_free_game()
elif page == "challenge":
    page_challenge()
elif page == "teacher":
    page_teacher()
else:
    st.session_state.page = "home"
    st.rerun()


st.markdown(
    '<div class="footer-note">'
    'Ludothèque Physique-Chimie · Plateforme pédagogique de jeux et d’activités interactives'
    '</div>',
    unsafe_allow_html=True,
)
