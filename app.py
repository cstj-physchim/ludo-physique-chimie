# VERSION_UI_2026_08_25_EXERCISE1_PER_QUESTION_BUTTONS_V8
import re
import base64
import json
import random
import textwrap
import secrets
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import qrcode
from PIL import Image

import streamlit as st
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
    """Limite le prototype de pilotage des contenus au compte de Christophe."""
    teacher_id = str(teacher_id or st.session_state.get("teacher_id", "")).strip().lower()
    teacher_name = str(teacher_name or st.session_state.get("teacher_name", "")).strip().lower()
    return (
        "christophe" in teacher_name
        or "declerck" in teacher_name
        or "christophe" in teacher_id
        or "declerck" in teacher_id
    )


PILOT_CONTENTS = {
    "exercise1_states_water": {
        "label": "Exercice 1 — Identifier les états de l’eau",
        "chapter": "Chapitre 1 — Organisation de la matière",
        "order": 5,
        "description": "Choisir, pour chaque situation, le ou les états physiques de l’eau correspondants.",
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

    if resource_is_available_for_current_user("exercise1_states_water"):
        exercises.append({
            "icon": "💧",
            "title": "Exercice 1 — Identifier les états de l’eau",
            "description": "Associe chaque situation au bon état physique : solide, liquide ou gazeux.",
            "color": "card-cyan",
            "page": "exercise1_states_water",
            "key": "start_ex14_states_water",
        })

    if states_matter_available_for_current_user():
        exercises.append({
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

    for exercise in exercises:
        c1, c2 = st.columns([4.5, 1.5])
        with c1:
            nav_card(
                exercise["icon"],
                exercise["title"],
                exercise["description"],
                exercise["color"],
            )
        with c2:
            st.write("")
            st.write("")
            st.button(
                "Commencer →",
                key=exercise["key"],
                use_container_width=True,
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
    """Correction immédiate d'une cellule au clic.

    États possibles :
    - idle : blanc
    - correct : vert
    - wrong : rouge
    """
    key = f"ex1_water_cell_{index}_{state_name}"
    clicked_label = {
        "solid": "Solide",
        "liquid": "Liquide",
        "gas": "Gazeux",
    }[state_name]

    is_correct = clicked_label in correct_states

    if is_correct:
        st.session_state[key] = "correct"
        st.session_state[f"ex1_water_valid_{index}_{state_name}"] = True
    else:
        st.session_state[key] = "wrong"
        err_key = f"ex1_water_errors_{index}"
        st.session_state[err_key] = int(st.session_state.get(err_key, 0)) + 1

    # Une ligne est considérée comme réussie si toutes les bonnes cases ont été trouvées
    # et qu'aucune mauvaise case n'est actuellement marquée comme juste.
    required = {
        "Solide": "solid",
        "Liquide": "liquid",
        "Gazeux": "gas",
    }
    all_good_found = all(
        st.session_state.get(f"ex1_water_cell_{index}_{required[label]}") == "correct"
        for label in correct_states
    )
    st.session_state[f"ex1_water_row_complete_{index}"] = all_good_found


def _ex1_render_answer_button(index, state_name, correct_states):
    state = _ex1_cell_state(index, state_name)

    state_label = {
        "solid": "Solide",
        "liquid": "Liquide",
        "gas": "Gazeux",
    }[state_name]

    if state == "idle":
        label = state_label
        button_type = "secondary"
    elif state == "correct":
        label = f"✓ {state_label}"
        button_type = "primary"
    else:
        label = f"✕ {state_label}"
        button_type = "secondary"

    st.button(
        label,
        key=f"ex1_click_{index}_{state_name}",
        use_container_width=True,
        type=button_type,
        on_click=_ex1_handle_cell_click,
        args=(index, state_name, correct_states),
    )

    state_class = {
        "idle": "ex1-choice-idle",
        "correct": "ex1-choice-correct",
        "wrong": "ex1-choice-wrong",
    }[state]

    st.markdown(
        f'<div class="{state_class}" data-ex1="{index}-{state_name}"></div>',
        unsafe_allow_html=True,
    )

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
            padding: .9rem 1.1rem;
            color: #324a68;
            margin: .4rem 0 1rem 0;
        }

        .ex1-question-card {
            background: #f1f3f6;
            border: 1px solid #dfe6ef;
            border-radius: 16px;
            padding: .85rem 1rem .95rem 1rem;
            margin-bottom: .75rem;
            box-shadow: 0 3px 10px rgba(31, 55, 90, .04);
        }

        .ex1-question-title {
            font-weight: 800;
            color: #162b4d;
            font-size: 1.02rem;
            margin-bottom: .55rem;
        }

        .ex1-feedback-hint {
            background: #fff7e6;
            border: 1px solid #f4d69b;
            border-radius: 12px;
            padding: .65rem .8rem;
            margin: .45rem 0 0 0;
            color: #73541c;
        }

        .ex1-feedback-correction {
            background: #fff1f1;
            border: 1px solid #f0c8c8;
            border-radius: 12px;
            padding: .65rem .8rem;
            margin: .45rem 0 0 0;
            color: #7b2c2c;
        }

        .ex1-feedback-ok {
            background: #eefaf2;
            border: 1px solid #cdebd6;
            border-radius: 12px;
            padding: .6rem .8rem;
            margin: .45rem 0 0 0;
            color: #24623a;
        }

        /* Boutons des réponses */
        div[data-testid="stButton"] button {
            min-height: 46px;
            font-weight: 800;
            border-radius: 12px;
        }

        /* Choix au repos */
        div[data-testid="stButton"] button[kind="secondary"] {
            background: #ffffff;
            border: 2px solid #cfd8e6;
            color: #18345d;
        }

        /* Bon choix */
        div[data-testid="stButton"] button[kind="primary"] {
            background: #2fb05b !important;
            border-color: #268f4b !important;
            color: #ffffff !important;
        }

        /* Mauvais choix */
        div[data-testid="stButton"]:has(+ .ex1-choice-wrong) button {
            background: #e05656 !important;
            border-color: #bd3d3d !important;
            color: #ffffff !important;
        }

        /* Repos */
        div[data-testid="stButton"]:has(+ .ex1-choice-idle) button {
            background: #ffffff !important;
            border-color: #cfd8e6 !important;
            color: #18345d !important;
        }

        /* Correct */
        div[data-testid="stButton"]:has(+ .ex1-choice-correct) button {
            background: #2fb05b !important;
            border-color: #268f4b !important;
            color: #ffffff !important;
        }

        .ex1-reset-row {
            margin-top: .75rem;
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
            <strong>ℹ️ Consigne :</strong> Pour chaque proposition, clique sur l’état ou les états physiques correspondants.<br>
            <span style="opacity:.82;">La correction apparaît immédiatement. Certaines propositions peuvent avoir plusieurs bonnes réponses.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for index, item in enumerate(EXERCISE1_STATES_WATER):
        st.markdown(
            f'<div class="ex1-question-card"><div class="ex1-question-title">{item["label"]}</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3, gap="small")

        with c1:
            _ex1_render_answer_button(index, "solid", item["answers"])

        with c2:
            _ex1_render_answer_button(index, "liquid", item["answers"])

        with c3:
            _ex1_render_answer_button(index, "gas", item["answers"])

        st.markdown("</div>", unsafe_allow_html=True)

        error_count = int(st.session_state.get(f"ex1_water_errors_{index}", 0))
        row_complete = bool(st.session_state.get(f"ex1_water_row_complete_{index}", False))

        if row_complete:
            st.markdown(
                f'<div class="ex1-feedback-ok">✅ <strong>{item["label"]}</strong> : bonne réponse.</div>',
                unsafe_allow_html=True,
            )
        elif error_count == 1:
            st.markdown(
                f'<div class="ex1-feedback-hint">💡 <strong>Indice — {item["label"]}</strong> : '
                f'{ex1_hint_for_item(item["label"])}</div>',
                unsafe_allow_html=True,
            )
        elif error_count >= 2:
            correct_text = " + ".join(sorted(item["answers"]))
            st.markdown(
                f'<div class="ex1-feedback-correction">❌ <strong>{item["label"]}</strong> : '
                f'la bonne réponse est <strong>{correct_text}</strong>.<br>'
                f'📘 {item["explanation"]}</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div class='ex1-reset-row'></div>", unsafe_allow_html=True)

    reset_col, spacer = st.columns([1.4, 3.6])
    with reset_col:
        if st.button(
            "↻ Réinitialiser",
            use_container_width=True,
            key="restart_ex1_states_water",
        ):
            reset_exercise1_states_water()
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

def teacher_header(title):
    st.markdown(
        f"""
        <div class="teacher-band">
            <div class="teacher-band-title">👨‍🏫 {current_teacher_name()} — {title}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.4, 1.1, 4.5])

    with c1:
        st.button(
            "← Tableau de bord",
            use_container_width=True,
            on_click=set_teacher_section,
            args=("dashboard",),
            key=f"teacher_back_dashboard_{title}",
        )

    with c2:
        st.button(
            "🏠 Accueil",
            use_container_width=True,
            on_click=set_page,
            args=("home",),
            key=f"teacher_home_{title}",
        )

    with c3:
        st.button(
            "Déconnexion",
            use_container_width=False,
            key=f"teacher_logout_{title}",
            on_click=logout_app,
        )


def teacher_dashboard():
    # Affiche immédiatement un écran de transition au-dessus de l'ancienne page.
    # Streamlit met à jour le DOM progressivement : sans ce masque, les anciennes
    # cartes de l'accueil restent visibles pendant les appels réseau Upstash.
    loading = st.empty()
    loading.markdown(
        """
        <style>
        .teacher-loading-overlay {
            position: fixed;
            inset: 0;
            z-index: 999999;
            background: rgba(248, 251, 255, 0.98);
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(2px);
        }
        .teacher-loading-card {
            background: white;
            border: 1px solid #dfe7f3;
            border-radius: 24px;
            padding: 28px 34px;
            box-shadow: 0 18px 50px rgba(31, 55, 90, 0.14);
            text-align: center;
            color: #153160;
            font-family: Arial, Helvetica, sans-serif;
        }
        .teacher-loading-icon {
            font-size: 2.4rem;
            margin-bottom: .55rem;
        }
        .teacher-loading-title {
            font-size: 1.12rem;
            font-weight: 800;
            margin-bottom: .3rem;
        }
        .teacher-loading-text {
            color: #60728c;
            font-size: .92rem;
        }
        </style>
        <div class="teacher-loading-overlay">
            <div class="teacher-loading-card">
                <div class="teacher-loading-icon">🧪</div>
                <div class="teacher-loading-title">Ouverture de l’espace professeur…</div>
                <div class="teacher-loading-text">Chargement de vos classes et résultats</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Les lectures réseau sont faites AVANT d'afficher le nouveau tableau de bord.
    # Ainsi on ne mélange plus visuellement l'ancien accueil et le nouvel écran.
    classes = get_classes()
    students = get_students()
    challenges = get_challenges()
    results = get_results()

    open_challenges = sum(1 for c in challenges if c.get("status") == "open")
    pilot_contents = content_pilot_enabled_for_teacher()

    # Les données sont prêtes : on retire le masque puis on construit la page complète.
    loading.empty()

    hero()

    nav1, nav2 = st.columns([1.4, 4.6])

    with nav1:
        st.button(
            "🏠 Retour à l'accueil",
            use_container_width=True,
            key="teacher_home_button",
            on_click=set_page,
            args=("home",),
        )

    with nav2:
        st.button(
            "Déconnexion",
            use_container_width=False,
            key="teacher_logout_button",
            on_click=logout_app,
        )

    st.markdown(
        f"""
        <div class="teacher-band">
            <div class="teacher-band-title">👨‍🏫 Espace professeur — {current_teacher_name()}</div>
            <div>Gérez vos classes et élèves, vos défis et vos résultats.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            f"{len(get_activity_log())} activité(s) enregistrée(s)",
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

    with st.expander("⚠️ Administration et réinitialisation"):
        st.warning(
            "Les suppressions effectuées ici concernent uniquement votre espace professeur "
            "et sont irréversibles."
        )

        reset_choice = st.selectbox(
            "Que voulez-vous réinitialiser ?",
            [
                "Défis",
                "Résultats",
                "Suivi pédagogique",
                "Élèves",
                "Classes et élèves",
                "Toutes les données",
            ],
            key="reset_choice",
        )

        reset_config = {
            "Défis": {
                "phrase": "SUPPRIMER LES DEFIS",
                "button": "🗑️ Supprimer tous les défis",
                "message": (
                    "Les défis seront supprimés, ainsi que les équipes collaboratives "
                    "qui leur sont associées. Les classes, élèves et résultats passés "
                    "seront conservés."
                ),
                "success": "Tous les défis ont été supprimés.",
            },
            "Résultats": {
                "phrase": "SUPPRIMER LES RESULTATS",
                "button": "🗑️ Supprimer tous les résultats",
                "message": (
                    "Tous les résultats enregistrés seront supprimés. "
                    "Les classes, élèves et défis seront conservés."
                ),
                "success": "Tous les résultats ont été supprimés.",
            },
            "Suivi pédagogique": {
                "phrase": "SUPPRIMER LE SUIVI",
                "button": "🗑️ Supprimer le suivi pédagogique",
                "message": (
                    "Les réalisations d'exercices et les préparations d'évaluation seront supprimées. "
                    "Les élèves, contenus, défis et résultats des défis seront conservés."
                ),
                "success": "Le suivi pédagogique a été supprimé.",
            },
            "Élèves": {
                "phrase": "SUPPRIMER LES ELEVES",
                "button": "🗑️ Supprimer tous les élèves",
                "message": (
                    "Tous les élèves seront supprimés, mais les classes resteront disponibles. "
                    "Les résultats déjà enregistrés sont conservés comme historique."
                ),
                "success": "Tous les élèves ont été supprimés.",
            },
            "Classes et élèves": {
                "phrase": "SUPPRIMER CLASSES ET ELEVES",
                "button": "🗑️ Supprimer les classes et les élèves",
                "message": (
                    "Toutes les classes et tous les élèves seront supprimés. "
                    "Les défis et les résultats déjà enregistrés seront conservés."
                ),
                "success": "Toutes les classes et tous les élèves ont été supprimés.",
            },
            "Toutes les données": {
                "phrase": "REINITIALISER TOUT",
                "button": "🗑️ Réinitialiser tout mon espace",
                "message": (
                    "Les classes, élèves, défis, équipes collaboratives et résultats "
                    "seront définitivement supprimés."
                ),
                "success": "Votre espace professeur a été entièrement réinitialisé.",
            },
        }

        config = reset_config[reset_choice]
        st.info(config["message"])

        reset_confirmation = st.text_input(
            f"Pour confirmer, saisissez exactement : {config['phrase']}",
            key="reset_confirmation",
        )

        if st.button(
            config["button"],
            disabled=reset_confirmation != config["phrase"],
            use_container_width=True,
            key="reset_action_button",
        ):
            if reset_choice == "Défis":
                reset_challenges()
            elif reset_choice == "Résultats":
                reset_results()
            elif reset_choice == "Suivi pédagogique":
                reset_tracking()
            elif reset_choice == "Élèves":
                reset_students()
            elif reset_choice == "Classes et élèves":
                reset_classes_and_students()
            else:
                reset_database()

            for session_key in [
                "challenge_student",
                "active_challenge",
                "collab_team_code",
            ]:
                st.session_state.pop(session_key, None)

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


def teacher_contents():
    teacher_header("Contenus")

    if not content_pilot_enabled_for_teacher():
        st.info("Le pilotage des contenus est actuellement en phase de test sur un seul compte professeur.")
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



def teacher_tracking():
    teacher_header("Suivi des élèves")

    if not content_pilot_enabled_for_teacher():
        st.info("Le suivi pédagogique est actuellement en phase de test sur un seul compte professeur.")
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
            student_rows = [
                latest[(student.get("id"), rid)]
                for rid in resource_ids
                if (student.get("id"), rid) in latest
            ]

            if student_rows:
                best = max(int(r.get("score_percent", 0)) for r in student_rows)
                done = len(student_rows)
                last_activity = max(
                    str(r.get("finished_at", "")) for r in student_rows
                )
                attempts = sum(int(r.get("attempt_number", 1)) for r in student_rows)
                status = "✅ Actif" if done == len(resource_ids) and resource_ids else "🟠 En cours"
                result_text = f"{best} %"
            else:
                done = 0
                attempts = 0
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
            latest_all = latest_training_by_student_resource(rows)
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
                    average = round(
                        sum(int(r.get("score_percent", 0)) for r in done_rows)
                        / len(done_rows)
                    )
                    result = f"{average} %"

                    if done == total:
                        status = "✅ Terminée"
                        bonus = "+1 possible" if average >= threshold else "—"
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
            st.dataframe(
                prep_table,
                use_container_width=True,
                hide_index=True,
            )


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


def page_teacher():
    if not teacher_login():
        return

    section = st.session_state.get(
        "teacher_section",
        "dashboard",
    )

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
