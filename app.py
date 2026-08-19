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

from levels import LEVELS, LEVEL_NAMES


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Ludothèque Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

ASSETS = Path("assets/molecules")

redis = Redis(
    url=st.secrets["UPSTASH_REDIS_REST_URL"],
    token=st.secrets["UPSTASH_REDIS_REST_TOKEN"],
)

CLASSES_KEY = "ludo:classes"
CHALLENGES_KEY = "ludo:challenges"
STUDENTS_KEY = "ludo:students"
RESULTS_KEY = "ludo:results"

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

    .hero {
        background: linear-gradient(135deg, #102a56 0%, #193c75 100%);
        color: white;
        border-radius: 24px;
        padding: 1.35rem 1.7rem;
        margin-bottom: 1.4rem;
        box-shadow: 0 12px 30px rgba(16, 42, 86, 0.16);
    }

    .hero-title {
        font-size: 2.25rem;
        font-weight: 800;
        margin: 0;
        line-height: 1.1;
    }

    .hero-subtitle {
        font-size: 1.05rem;
        margin-top: 0.35rem;
        opacity: 0.9;
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
    st.markdown(
        """
        <div class="hero">
            <div class="hero-title">🧪 Ludothèque Physique-Chimie</div>
            <div class="hero-subtitle">
                Apprendre en jouant, progresser avec plaisir !
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
# CLASSES
# ============================================================

def get_classes():
    return sorted(set(redis_read_json(CLASSES_KEY, [])))


def add_class(class_name):
    class_name = class_name.strip().upper()
    if not class_name:
        return False

    classes = get_classes()
    if class_name in classes:
        return False

    classes.append(class_name)
    redis_write_json(CLASSES_KEY, sorted(classes))
    return True


# ============================================================
# ÉLÈVES
# ============================================================

def get_students():
    return redis_read_json(STUDENTS_KEY, [])


def save_students(students):
    redis_write_json(STUDENTS_KEY, students)


def generate_student_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    existing = {s["code"] for s in get_students()}

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

    for student in get_students():
        if student.get("active", True) and student["code"] == code:
            return student

    return None


def find_student_by_id(student_id):
    student_id = str(student_id).strip()

    for student in get_students():
        if student.get("active", True) and student["id"] == student_id:
            return student

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
    redis_write_json(CLASSES_KEY, classes)
    return True, None


def reset_database():
    """
    Réinitialisation complète des données pédagogiques.
    Les clés Upstash sont conservées mais remises à des listes vides.
    """
    redis_write_json(CLASSES_KEY, [])
    redis_write_json(STUDENTS_KEY, [])
    redis_write_json(CHALLENGES_KEY, [])
    redis_write_json(RESULTS_KEY, [])


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
    return redis_read_json(CHALLENGES_KEY, [])


def save_challenges(challenges):
    redis_write_json(CHALLENGES_KEY, challenges)


def generate_challenge_code():
    existing = {str(c["code"]) for c in get_challenges()}

    for _ in range(100):
        code = str(random.randint(1000, 9999))
        if code not in existing:
            return code

    raise RuntimeError("Impossible de générer un code de défi unique.")


def create_challenge(class_name, activity, theme, level, max_attempts):
    challenges = get_challenges()

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
    }

    challenges.append(challenge)
    save_challenges(challenges)

    return challenge


def close_challenge(code):
    challenges = get_challenges()

    for challenge in challenges:
        if str(challenge["code"]) == str(code):
            challenge["status"] = "closed"

    save_challenges(challenges)


def find_open_challenge(code):
    code = code.strip()

    for challenge in get_challenges():
        if str(challenge["code"]) == code and challenge["status"] == "open":
            return challenge

    return None


# ============================================================
# RÉSULTATS
# ============================================================

def get_results():
    return redis_read_json(RESULTS_KEY, [])


def save_result(student, challenge, errors, elapsed):
    results = get_results()

    previous = [
        r
        for r in results
        if r["student_id"] == student["id"]
        and str(r["challenge_code"]) == str(challenge["code"])
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
    redis_write_json(RESULTS_KEY, results)

    return True, result


def attempts_used(student, challenge):
    return len(
        [
            r
            for r in get_results()
            if r["student_id"] == student["id"]
            and str(r["challenge_code"]) == str(challenge["code"])
        ]
    )


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


def formula_block(formula):
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
        str(ASSETS / f"{image_name}.svg"),
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
            current_index = LEVEL_NAMES.index(level)

            st.markdown("### Que veux-tu faire maintenant ?")

            left, right = st.columns(2)

            with left:
                if st.button(
                    "🔄 Rejouer le même niveau",
                    key=f"replay_{level}",
                    use_container_width=True,
                ):
                    init_game(level, suffix)
                    st.rerun()

            with right:
                if current_index < len(LEVEL_NAMES) - 1:
                    next_level = LEVEL_NAMES[current_index + 1]

                    if st.button(
                        f"➡️ Passer au niveau suivant : "
                        f"{LEVELS[next_level]['emoji']} {next_level}",
                        key=f"next_{level}",
                        type="primary",
                        use_container_width=True,
                    ):
                        st.session_state.selected_level = next_level
                        init_game(next_level, suffix)
                        st.rerun()
                else:
                    if st.button(
                        "🏆 Recommencer depuis le niveau Facile",
                        key="restart_all",
                        type="primary",
                        use_container_width=True,
                    ):
                        first = LEVEL_NAMES[0]
                        st.session_state.selected_level = first
                        init_game(first, suffix)
                        st.rerun()


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
            "Associer composants et symboles électriques.",
            "card-orange",
            coming_soon=True,
        )
        st.button(
            "Bientôt disponible",
            key="theme_elec",
            use_container_width=True,
            disabled=True,
        )


def page_free_level():
    hero()
    back_button("free_theme")

    st.markdown(
        '<div class="breadcrumb">Accueil › Entraînement libre › Dominos › Molécules › Niveau</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">Choisissez votre niveau</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(4)

    for i, level in enumerate(LEVEL_NAMES):
        with cols[i]:
            icon = LEVELS[level]["emoji"]
            color = ["card-green", "card-orange", "card-pink", "card-purple"][i]

            nav_card(
                icon,
                level,
                "Lancez une nouvelle partie de dominos molécules.",
                color,
            )

            if st.button(
                f"Jouer — {level}",
                key=f"level_{level}",
                use_container_width=True,
            ):
                st.session_state.selected_level = level
                init_game(level, "free")
                go("free_game")


def page_free_game():
    hero()
    back_button("free_level")

    level = st.session_state.get(
        "selected_level",
        LEVEL_NAMES[0],
    )

    st.markdown(
        f'<div class="breadcrumb">Accueil › Entraînement libre › Dominos › Molécules › {level}</div>',
        unsafe_allow_html=True,
    )

    st.subheader(
        f"🁢 Dominos — Molécules · {LEVELS[level]['emoji']} {level}"
    )

    domino_game(level, suffix="free")


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
                found = find_open_challenge(used_code)

                if not found:
                    st.error("Ce défi n'existe pas ou il est fermé.")
                elif found["class_name"] != student["class_name"]:
                    st.error("Ce défi n'est pas destiné à votre classe.")
                elif attempts_used(student, found) >= int(found["max_attempts"]):
                    st.error("Toutes les tentatives autorisées ont déjà été utilisées.")
                elif found.get("activity", "Dominos") != "Dominos" or found.get("theme", "Molécules") != "Molécules":
                    st.error("Cette activité n'est pas encore disponible dans cette version.")
                else:
                    st.session_state.active_challenge = found
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

    st.write(
        f"**Classe :** {challenge['class_name']}  ·  "
        f"**Niveau :** {LEVELS[challenge['level']]['emoji']} {challenge['level']}  ·  "
        f"**Tentatives autorisées :** {challenge['max_attempts']}"
    )

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

    password = st.text_input(
        "Mot de passe",
        type="password",
        key="teacher_password",
    )

    if st.button(
        "Se connecter",
        type="primary",
        use_container_width=True,
        key="teacher_login",
    ):
        expected = st.secrets.get("TEACHER_PASSWORD", "")

        if not expected:
            st.error("Le secret TEACHER_PASSWORD n'est pas configuré.")
        elif password == expected:
            st.session_state.teacher_authenticated = True
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
            <div class="teacher-band-title">👨‍🏫 Espace professeur — {title}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 5])

    with c1:
        if st.button("← Tableau de bord", use_container_width=True):
            st.session_state.teacher_section = "dashboard"
            st.rerun()

    with c2:
        if st.button("Déconnexion", use_container_width=False):
            st.session_state.teacher_authenticated = False
            st.session_state.teacher_section = "dashboard"
            go("home")


def teacher_dashboard():
    hero()

    st.markdown(
        """
        <div class="teacher-band">
            <div class="teacher-band-title">👨‍🏫 Espace professeur</div>
            <div>Gérez votre Ludothèque depuis ce tableau de bord.</div>
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
            "La réinitialisation complète efface les classes, les élèves, "
            "les défis et tous les résultats. Cette action est irréversible."
        )

        reset_confirmation = st.text_input(
            "Pour confirmer, saisissez exactement : REINITIALISER",
            key="reset_database_confirmation",
        )

        if st.button(
            "🗑️ Réinitialiser toute la base de données",
            disabled=reset_confirmation != "REINITIALISER",
            use_container_width=True,
            key="reset_database_button",
        ):
            reset_database()

            for session_key in [
                "challenge_student",
                "active_challenge",
            ]:
                st.session_state.pop(session_key, None)

            st.success("Base de données réinitialisée.")
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

    template_df = make_student_template()

    st.download_button(
        "📄 Télécharger un exemple de structure",
        data=template_df.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="exemple_base_eleves.csv",
        mime="text/csv",
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
        c1, c2, c3, c4, c5 = st.columns(5)

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
                ["Molécules"],
                key="challenge_theme",
            )

        with c4:
            challenge_level = st.selectbox(
                "Niveau",
                LEVEL_NAMES,
                key="challenge_level",
                format_func=lambda x: f"{LEVELS[x]['emoji']} {x}",
            )

        with c5:
            max_attempts = st.selectbox(
                "Tentatives",
                [1, 2, 3],
                index=0,
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
            )

            st.success(
                f"Défi créé — code **{challenge['code']}** "
                f"pour **{challenge['class_name']}**."
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

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([1, 1.5, 2, 1, 1])

            with c1:
                st.markdown(f"### {challenge['code']}")
                st.write("🟢 Ouvert" if status_open else "⚫ Fermé")

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
                st.write(
                    f"**Tentatives :** {challenge['max_attempts']}"
                )

            with c5:
                if status_open:
                    if st.button(
                        "Fermer",
                        key=f"close_{challenge['code']}",
                        use_container_width=True,
                    ):
                        close_challenge(challenge["code"])
                        st.rerun()


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
        table.append(
            {
                "Rang": rank,
                "Élève": f"{r['first_name']} {r['last_initial']}.",
                "Classe": r["class_name"],
                "Défi": r["challenge_code"],
                "Activité": r.get("activity", "Dominos"),
                "Thème": r.get("theme", "Molécules"),
                "Niveau": r["level"],
                "Erreurs": r["errors"],
                "Temps": f"{r['time_seconds'] // 60}:{r['time_seconds'] % 60:02d}",
                "Tentative": r["attempt"],
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

st.caption(
    "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes "
    "— licence CC BY-NC-SA."
)
