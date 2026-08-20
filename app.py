import json
import random
import secrets
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from upstash_redis import Redis

from levels import LEVELS, LEVEL_NAMES, MOLECULE_LEVEL_NAMES, ELECTRICITY_LEVEL_NAMES


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Ludothèque Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

ASSETS = Path("assets/molecules")
ASSETS_ELECTRICITY = Path("assets/electricity")

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

    .footer-note {
        background: #eef6ff;
        border: 1px solid #d9eafa;
        border-radius: 14px;
        padding: 0.75rem 1rem;
        color: #45617f;
        text-align: center;
        margin-top: 1rem;
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


def go(page):
    st.session_state.page = page
    st.rerun()


def back_button(target="home", label="← Retour"):
    if st.button(label, use_container_width=False):
        go(target)


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
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    existing = set()
    for teacher_id in get_teacher_accounts():
        for student in redis_read_json(teacher_key("students", teacher_id), []):
            existing.add(student["code"])
    for _ in range(500):
        code = "".join(secrets.choice(alphabet) for _ in range(4))
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


# ============================================================
# QR ET PDF
# ============================================================

def student_qr_url(student):
    return f"{APP_PUBLIC_URL}/?student={student['id']}"


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

    qr_size = 31 * mm

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
            x,
            y,
            card_width,
            card_height,
            4 * mm,
            stroke=1,
            fill=0,
        )

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 8 * mm,
            "Ludothèque Physique-Chimie",
        )

        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 17 * mm,
            f"{student['first_name']} {student['last_initial']}.",
        )

        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 24 * mm,
            f"Classe : {student['class_name']}",
        )

        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 35 * mm,
            "Code personnel",
        )

        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 45 * mm,
            student["code"],
        )

        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(
            x + 5 * mm,
            y + 7 * mm,
            "Conserve cette carte pour l'année scolaire.",
        )

        qr_reader = ImageReader(BytesIO(make_qr_png_bytes(student)))

        qr_x = x + card_width - qr_size - 5 * mm
        qr_y = y + (card_height - qr_size) / 2 - 2 * mm

        pdf.drawImage(
            qr_reader,
            qr_x,
            qr_y,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )

        pdf.setFont("Helvetica", 6.5)
        pdf.drawCentredString(
            qr_x + qr_size / 2,
            qr_y - 2.5 * mm,
            "QR personnel Ludothèque",
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
    if str(image_name).startswith("elec_"):
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


def molecule_block(image_name):
    st.image(
        str(asset_path(image_name)),
        width=240,
    )


def show_domino(level, domino_id, key=None, clickable=False, reversed_domino=False):
    image_name, formula = LEVELS[level]["dominos"][domino_id]

    with st.container(border=True):
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
            "Observe l'extrémité libre du dernier domino posé et choisis, "
            "parmi tes cartes, celle dont le montage ou le schéma correspond."
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


# ============================================================
# NAVIGATION ÉLÈVE
# ============================================================

def page_home():
    hero()

    st.markdown(
        '<div class="section-title">Que voulez-vous faire aujourd’hui ?</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        nav_card(
            "🎮",
            "Entraînement libre",
            "Choisissez un jeu, un thème et un niveau puis entraînez-vous librement.",
            "card-blue",
        )
        if st.button(
            "Commencer  ›",
            key="home_free",
            use_container_width=True,
        ):
            go("free_activity")

    with c2:
        nav_card(
            "🏆",
            "Participer à un défi",
            "Entrez votre code personnel et le code du défi lancé par votre professeur.",
            "card-green",
        )
        if st.button(
            "Participer  ›",
            key="home_challenge",
            type="primary",
            use_container_width=True,
        ):
            go("challenge")

    with c3:
        nav_card(
            "🔒",
            "Espace professeur",
            "Gérez les classes, les élèves, les défis et consultez les résultats.",
            "card-purple",
        )
        if st.button(
            "Accéder  ›",
            key="home_teacher",
            use_container_width=True,
        ):
            go("teacher")


def page_free_activity():
    hero()
    back_button("home")

    st.markdown(
        '<div class="breadcrumb">Accueil › Entraînement libre › Choix de l’activité</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Choisissez votre activité</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(5)

    activities = [
        ("🁢", "Dominos", "Associez les dominos et construisez le bon chemin.", "card-blue", False),
        ("🧠", "Memory", "Retrouvez les paires correspondantes.", "card-pink", True),
        ("🔗", "Associations", "Associez les bonnes réponses.", "card-cyan", True),
        ("📝", "Exercices", "Répondez à des questions interactives.", "card-purple", True),
        ("⚡", "Défis rapides", "De courts défis pour tester vos connaissances.", "card-orange", True),
    ]

    for i, (icon, title, text, color, soon) in enumerate(activities):
        with cols[i]:
            nav_card(icon, title, text, color, coming_soon=soon)

            if title == "Dominos":
                if st.button(
                    "Choisir",
                    key="choose_dominos",
                    use_container_width=True,
                ):
                    go("free_theme")
            else:
                st.button(
                    "Bientôt disponible",
                    key=f"soon_{title}",
                    use_container_width=True,
                    disabled=True,
                )


def page_free_theme():
    hero()
    back_button("free_activity")

    st.markdown(
        '<div class="breadcrumb">Accueil › Entraînement libre › Dominos › Choix du thème</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Dominos — choisissez un thème</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        nav_card(
            "🔵",
            "Molécules",
            "Formules, modèles moléculaires et composition de la matière.",
            "card-blue",
        )
        if st.button(
            "Choisir Molécules",
            key="theme_molecules",
            use_container_width=True,
        ):
            st.session_state.selected_theme = "Molécules"
            go("free_level")

    with c2:
        nav_card(
            "➕➖",
            "Ions",
            "Reconnaître les ions et leurs formules.",
            "card-green",
            coming_soon=True,
        )
        st.button(
            "Bientôt disponible",
            key="theme_ions",
            use_container_width=True,
            disabled=True,
        )

    with c3:
        nav_card(
            "⚡",
            "Électricité",
            "Passer du montage électrique au schéma normalisé et réciproquement.",
            "card-orange",
        )
        if st.button(
            "Choisir Électricité",
            key="theme_elec",
            use_container_width=True,
        ):
            st.session_state.selected_theme = "Électricité"
            go("free_level")


def page_free_level():
    hero()
    back_button("free_theme")

    theme = st.session_state.get("selected_theme", "Molécules")
    theme_levels = levels_for_theme(theme)

    st.markdown(
        f'<div class="breadcrumb">Accueil › Entraînement libre › Dominos › {theme} › Niveau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Choisissez votre niveau</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(max(1, len(theme_levels)))

    for i, level in enumerate(theme_levels):
        with cols[i]:
            icon = LEVELS[level]["emoji"]
            colors = ["card-green", "card-orange", "card-pink", "card-purple"]
            color = "card-purple" if theme == "Électricité" else colors[i % len(colors)]

            description = (
                "Circuits en série : montage réel ↔ schéma normalisé."
                if theme == "Électricité"
                else "Lancez une nouvelle partie de dominos molécules."
            )

            nav_card(
                icon,
                level,
                description,
                color,
            )

            if st.button(
                f"Jouer — {level}",
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
        f'<div class="breadcrumb">Accueil › Entraînement libre › Dominos › {theme} › {level}</div>',
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

    if not st.session_state.get("challenge_student"):
        qr_student_id = st.query_params.get("student")

        if qr_student_id:
            qr_student = find_student_by_id(qr_student_id)

            if qr_student:
                st.session_state.challenge_student = qr_student

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

    if not student:
        st.write("Entrez votre **code personnel élève**.")

        student_code = st.text_input(
            "Code élève",
            max_chars=4,
            placeholder="Ex. K7P4",
            key="student_code_input",
        )

        if st.button(
            "Continuer",
            type="primary",
            use_container_width=True,
            key="identify_student",
        ):
            found = find_student_by_code(student_code)

            if found:
                st.session_state.challenge_student = found
                st.rerun()
            else:
                st.error("Code élève inconnu.")

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

        c1, c2 = st.columns(2)

        with c1:
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
                elif found.get("activity", "Dominos") != "Dominos" or found.get("theme", "Molécules") not in ("Molécules", "Électricité"):
                    st.error("Cette activité n'est pas encore disponible dans cette version.")
                else:
                    st.session_state.active_challenge = found

                    if found.get("mode", "Individuel") == "Collaboratif":
                        st.session_state.pop("collab_team_code", None)
                    else:
                        suffix = f"challenge_{found['code']}_{student['id']}"
                        init_game(found["level"], suffix)

                    st.rerun()

        with c2:
            if st.button(
                "Changer d'élève",
                use_container_width=True,
            ):
                st.session_state.pop("challenge_student", None)
                st.query_params.clear()
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
    if st.session_state.get("teacher_authenticated", False):
        return True

    hero()
    back_button("home")
    st.markdown(
        '<div class="section-title">🔒 Connexion professeur</div>',
        unsafe_allow_html=True,
    )

    accounts = get_teacher_accounts()
    if not accounts:
        st.error("Aucun compte professeur n'est configuré dans les Secrets Streamlit.")
        return False

    teacher_ids = list(accounts.keys())
    selected_id = st.selectbox(
        "Professeur",
        teacher_ids,
        format_func=lambda tid: accounts[tid]["name"],
        key="teacher_account_select",
    )
    password = st.text_input("Mot de passe", type="password", key="teacher_password")

    if st.button("Se connecter", type="primary", use_container_width=True, key="teacher_login"):
        if secrets.compare_digest(password, accounts[selected_id]["password"]):
            st.session_state.teacher_authenticated = True
            st.session_state.teacher_id = selected_id
            st.session_state.teacher_name = accounts[selected_id]["name"]
            st.session_state.teacher_section = "dashboard"
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
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

    c1, c2, c3, c4 = st.columns([1.3, 1.1, 1.5, 3.1])

    with c1:
        if st.button("← Tableau de bord", use_container_width=True):
            st.session_state.teacher_section = "dashboard"
            st.rerun()

    with c2:
        if st.button("🏠 Accueil", use_container_width=True):
            go("home")

    with c3:
        if st.button("🔄 Changer de professeur", use_container_width=True):
            clear_teacher_session()
            st.session_state.page = "teacher"
            st.rerun()

    with c4:
        if st.button("Déconnexion", use_container_width=False):
            clear_teacher_session()
            go("home")


def teacher_dashboard():
    hero()

    nav1, nav2, nav3, nav4 = st.columns([1.3, 1.7, 1.2, 2.8])

    with nav1:
        if st.button(
            "🏠 Retour à l'accueil",
            use_container_width=True,
            key="teacher_home_button",
        ):
            go("home")

    with nav2:
        if st.button(
            "🔄 Changer de professeur",
            use_container_width=True,
            key="teacher_change_button",
        ):
            clear_teacher_session()
            st.session_state.page = "teacher"
            st.rerun()

    with nav3:
        if st.button(
            "Déconnexion",
            use_container_width=True,
            key="teacher_logout_button",
        ):
            clear_teacher_session()
            go("home")

    st.markdown(
        f"""
        <div class="teacher-band">
            <div class="teacher-band-title">👨‍🏫 Espace professeur — {current_teacher_name()}</div>
            <div>Gérez vos classes, vos élèves, vos défis et vos résultats.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    classes = get_classes()
    students = get_students()
    challenges = get_challenges()
    results = get_results()

    open_challenges = sum(1 for c in challenges if c.get("status") == "open")

    cols = st.columns(4)

    cards = [
        (
            "🏫",
            "Classes",
            "Créez et gérez vos classes.",
            f"{len(classes)} classe(s)",
            "card-blue",
            "classes",
        ),
        (
            "👥",
            "Élèves",
            "Importez les élèves et générez les codes et QR.",
            f"{len(students)} élève(s)",
            "card-green",
            "students",
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

    for i, (icon, title, text, count, color, section) in enumerate(cards):
        with cols[i]:
            nav_card(icon, title, f"{text}<br><br><strong>{count}</strong>", color)

            if st.button(
                f"Gérer {title.lower()}  ›",
                key=f"teacher_{section}",
                use_container_width=True,
            ):
                st.session_state.teacher_section = section
                st.rerun()

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


def teacher_classes():
    teacher_header("Classes")

    st.subheader("Créer une classe")

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
        ):
            if add_class(class_name):
                st.success(
                    f"Classe {class_name.strip().upper()} créée."
                )
                st.rerun()
            else:
                st.warning(
                    "Cette classe existe déjà ou le nom est vide."
                )

    classes = get_classes()
    students = get_students()

    rows = []

    for class_item in classes:
        effectif = sum(
            1 for s in students if s["class_name"] == class_item
        )

        rows.append(
            {
                "Classe": class_item,
                "Effectif": effectif,
            }
        )

    if rows:
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.subheader("Supprimer une classe")

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


def teacher_students():
    teacher_header("Élèves")

    st.subheader("Importer une base élèves depuis Excel")

    st.write(
        "Le fichier doit contenir exactement les informations nécessaires : "
        "**Prénom**, **Initiale du nom** et **Classe**."
    )

    st.download_button(
        "📥 Télécharger le modèle Excel pour importer une classe",
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

            first_col, initial_col, class_col = detect_student_columns(
                excel_df
            )

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
            ):
                added, duplicates, errors = import_students_from_dataframe(
                    excel_df
                )

                if added:
                    st.success(
                        f"✅ {added} élève(s) importé(s). "
                        f"{duplicates} doublon(s) ignoré(s)."
                    )

                if errors:
                    st.warning(
                        f"{len(errors)} ligne(s) n'ont pas été importées."
                    )

                    for message in errors[:20]:
                        st.write("• " + message)

                if added:
                    st.rerun()

        except Exception as exc:
            st.error(
                "Impossible de lire ce fichier Excel. "
                f"Détail : {exc}"
            )

    st.markdown("---")
    st.subheader("Ajouter ponctuellement un élève")

    classes = get_classes()

    if classes:
        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            first_name = st.text_input(
                "Prénom",
                key="new_student_firstname",
            )

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
        ):
            student, error = add_student(
                first_name,
                last_initial,
                student_class,
            )

            if error:
                st.error(error)
            else:
                st.success(
                    f"Élève ajouté — code **{student['code']}**"
                )
                st.rerun()

    st.markdown("---")
    st.subheader("Élèves enregistrés")

    students = get_students()

    if not students:
        st.info("Aucun élève enregistré.")
        return

    filter_classes = ["Toutes"] + get_classes()

    selected_filter = st.selectbox(
        "Filtrer par classe",
        filter_classes,
        key="student_filter",
    )

    filtered = [
        s
        for s in students
        if (
            selected_filter == "Toutes"
            or s["class_name"] == selected_filter
        )
    ]

    if filtered:
        pdf_cards = generate_student_cards_pdf(filtered)

        filename = (
            "cartes_eleves_ludotheque_toutes_classes.pdf"
            if selected_filter == "Toutes"
            else f"cartes_eleves_ludotheque_{selected_filter}.pdf"
        )

        st.download_button(
            "🖨️ Télécharger les cartes élèves en PDF (code + QR)",
            data=pdf_cards,
            file_name=filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

    table = [
        {
            "Prénom": s["first_name"],
            "Initiale": s["last_initial"] + ".",
            "Classe": s["class_name"],
            "Code": s["code"],
        }
        for s in sorted(
            filtered,
            key=lambda s: (
                s["class_name"],
                s["first_name"].lower(),
                s["last_initial"],
            ),
        )
    ]

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("Retirer un élève")

    student_options = {
        f"{s['first_name']} {s['last_initial']}. — {s['class_name']} — {s['code']}": s["id"]
        for s in sorted(
            filtered,
            key=lambda s: (
                s["class_name"],
                s["first_name"].lower(),
                s["last_initial"],
            ),
        )
    }

    if student_options:
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
                ["Molécules", "Électricité"],
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
    elif section == "classes":
        teacher_classes()
    elif section == "students":
        teacher_students()
    elif section == "challenges":
        teacher_challenges()
    elif section == "results":
        teacher_results()


# ============================================================
# ROUTEUR PRINCIPAL
# ============================================================

if "page" not in st.session_state:
    st.session_state.page = "home"

page = st.session_state.page

if page == "home":
    page_home()
elif page == "free_activity":
    page_free_activity()
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
