import json
import random
import secrets
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from upstash_redis import Redis
from levels import LEVELS, LEVEL_NAMES

st.set_page_config(
    page_title="Ludo Physique-Chimie",
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

# URL utilisée dans les QR codes élèves.
# Si tu ajoutes APP_PUBLIC_URL dans les Secrets Streamlit, elle sera utilisée.
# Sinon Ludo utilise l'adresse publique actuelle de l'application.
APP_PUBLIC_URL = st.secrets.get(
    "APP_PUBLIC_URL",
    "https://ludo-physique-chimie.streamlit.app",
).rstrip("/")


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
    code = generate_student_code()
    student_id = secrets.token_urlsafe(12)

    student = {
        "id": student_id,
        "code": code,
        "first_name": first_name,
        "last_initial": last_initial,
        "class_name": class_name,
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    students.append(student)
    save_students(students)
    return student, None



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
    normalized = {
        normalize_column_name(col): col
        for col in df.columns
    }

    first_name_candidates = [
        "prenom",
        "prénom",
        "first name",
        "firstname",
    ]

    last_name_candidates = [
        "nom",
        "nom de famille",
        "last name",
        "lastname",
    ]

    initial_candidates = [
        "initiale",
        "initiale nom",
        "initiale du nom",
    ]

    class_candidates = [
        "classe",
        "class",
        "division",
    ]

    def find_candidate(candidates):
        for candidate in candidates:
            key = normalize_column_name(candidate)
            if key in normalized:
                return normalized[key]
        return None

    first_col = find_candidate(first_name_candidates)
    last_col = find_candidate(last_name_candidates)
    initial_col = find_candidate(initial_candidates)
    class_col = find_candidate(class_candidates)

    return first_col, last_col, initial_col, class_col


def import_students_from_dataframe(df):
    first_col, last_col, initial_col, class_col = detect_student_columns(df)

    if not first_col:
        return 0, 0, ["Colonne Prénom introuvable."]
    if not class_col:
        return 0, 0, ["Colonne Classe introuvable."]
    if not last_col and not initial_col:
        return 0, 0, ["Il faut une colonne Nom ou Initiale du nom."]

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

        if initial_col:
            last_initial = str(row.get(initial_col, "")).strip().upper().replace(".", "")[:1]
        else:
            last_name = str(row.get(last_col, "")).strip()
            last_initial = last_name[:1].upper() if last_name else ""

        # Ignore fully empty rows
        if not first_name and not class_name and not last_initial:
            continue

        if not first_name or not class_name or not last_initial:
            errors.append(
                f"Ligne {row_number} : prénom, nom/initiale ou classe manquant."
            )
            continue

        key = (
            first_name.lower(),
            last_initial,
            class_name,
        )

        if key in existing_keys:
            duplicates += 1
            continue

        # Add class automatically if it does not exist yet
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
            {"Prénom": "Emma", "Nom": "Durand", "Classe": "4B"},
            {"Prénom": "Lucas", "Nom": "Martin", "Classe": "4B"},
        ]
    )

def find_student_by_code(code):
    code = code.strip().upper()
    for student in get_students():
        if student.get("active", True) and student["code"] == code:
            return student
    return None


def find_student_by_id(student_id):
    student_id = str(student_id).strip()

    for student in get_students():
        if (
            student.get("active", True)
            and student["id"] == student_id
        ):
            return student

    return None


def student_qr_url(student):
    """
    Le QR ne contient ni prénom, ni classe, ni code visible.
    Il contient uniquement l'identifiant aléatoire interne de l'élève.
    """
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


def generate_student_cards_pdf(students, title="Ludo Physique-Chimie"):
    """
    Génère un PDF A4 de 8 cartes par page (2 colonnes x 4 lignes).
    Chaque carte contient : prénom + initiale, classe, code personnel et QR.
    """
    buffer = BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4,
    )

    page_width, page_height = A4

    margin_x = 10 * mm
    margin_y = 10 * mm
    gap_x = 6 * mm
    gap_y = 5 * mm

    cols = 2
    rows = 4

    card_width = (
        page_width
        - 2 * margin_x
        - gap_x
    ) / cols

    card_height = (
        page_height
        - 2 * margin_y
        - 3 * gap_y
    ) / rows

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

        x = (
            margin_x
            + col * (card_width + gap_x)
        )

        y = (
            page_height
            - margin_y
            - (row + 1) * card_height
            - row * gap_y
        )

        # Bordure de la carte
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

        # En-tête
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            x + 5 * mm,
            y + card_height - 8 * mm,
            title,
        )

        # Identité minimale
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

        # Code personnel
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

        # QR code
        qr_bytes = make_qr_png_bytes(student)

        from reportlab.lib.utils import ImageReader

        qr_reader = ImageReader(
            BytesIO(qr_bytes)
        )

        qr_x = (
            x
            + card_width
            - qr_size
            - 5 * mm
        )

        qr_y = (
            y
            + (card_height - qr_size) / 2
            - 2 * mm
        )

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
            "QR personnel Ludo",
        )

    pdf.save()

    buffer.seek(0)
    return buffer.getvalue()


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


def create_challenge(class_name, level, max_attempts):
    challenges = get_challenges()
    challenge = {
        "code": generate_challenge_code(),
        "class_name": class_name,
        "game": "Dominos — Molécules",
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


def get_results():
    return redis_read_json(RESULTS_KEY, [])


def save_result(student, challenge, errors, elapsed):
    results = get_results()
    previous = [
        r for r in results
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
    return len([
        r for r in get_results()
        if r["student_id"] == student["id"]
        and str(r["challenge_code"]) == str(challenge["code"])
    ])


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
        f"""<div style="
        min-height:115px;display:flex;align-items:center;justify-content:center;
        font-size:1.55rem;text-align:center;font-weight:500;">{formula}</div>""",
        unsafe_allow_html=True,
    )


def molecule_block(image_name):
    st.image(str(ASSETS / f"{image_name}.svg"), width=240)


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
            return st.button("Placer", key=key, use_container_width=True)
    return False


def show_turn(direction):
    """
    Virage du serpent : la chaîne descend verticalement avant de repartir
    dans l'autre sens. La flèche est donc volontairement verticale.
    """
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
                show_domino(level, domino_id, reversed_domino=not going_right)
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
        if st.button("🔄 Nouvelle partie", key=f"new_{suffix}_{level}", use_container_width=True):
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
                        level, did,
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
                st.error("Ce domino ne correspond pas. Observe à nouveau l'extrémité de la chaîne.")
    else:
        elapsed = int(time.time() - game["started"])
        st.markdown("---")
        st.markdown("## 🎉 Niveau terminé !")

        r1, r2, r3 = st.columns(3)
        with r1:
            st.metric("Erreurs", game["errors"])
        with r2:
            st.metric("Temps", f"{elapsed // 60} min {elapsed % 60:02d} s")
        with r3:
            st.metric("Dominos", f"{total}/{total}")

        if game["errors"] == 0:
            st.success("🎯 Badge obtenu : Sans faute")

        if challenge and student and not game["saved"]:
            ok, result = save_result(student, challenge, game["errors"], elapsed)
            game["saved"] = True
            if ok:
                st.success(
                    f"✅ Résultat enregistré — tentative {result['attempt']} / "
                    f"{challenge['max_attempts']}."
                )
            else:
                st.warning(result)

        if challenge and student:
            used = attempts_used(student, challenge)
            remaining_attempts = max(0, int(challenge["max_attempts"]) - used)

            if remaining_attempts > 0:
                if st.button(
                    f"🔄 Rejouer le défi ({remaining_attempts} tentative(s) restante(s))",
                    key=f"retry_challenge_{challenge['code']}",
                    use_container_width=True,
                ):
                    init_game(level, suffix)
                    st.rerun()
            else:
                st.info("🏁 Toutes les tentatives autorisées pour ce défi ont été utilisées.")

            if st.button(
                "🚪 Quitter le défi",
                key=f"leave_{challenge['code']}",
                use_container_width=True,
            ):
                st.session_state.pop("challenge_student", None)
                st.session_state.pop("active_challenge", None)
                st.query_params.clear()
                st.rerun()
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


def page_free_play():
    st.subheader("🁢 Dominos — Molécules")
    if "selected_level" not in st.session_state:
        st.session_state.selected_level = LEVEL_NAMES[0]

    level = st.selectbox(
        "Choisis ton niveau",
        LEVEL_NAMES,
        key="selected_level",
        format_func=lambda x: f"{LEVELS[x]['emoji']} {x}",
    )
    domino_game(level, suffix="free")


def page_join_challenge():
    st.subheader("🏆 Participer à un défi")

    # Si l'élève arrive grâce à son QR personnel,
    # on récupère automatiquement son identifiant dans l'URL.
    if not st.session_state.get("challenge_student"):
        qr_student_id = st.query_params.get("student")

        if qr_student_id:
            qr_student = find_student_by_id(qr_student_id)

            if qr_student:
                st.session_state.challenge_student = qr_student

    student = st.session_state.get("challenge_student")
    challenge = st.session_state.get("active_challenge")

    if not student:
        st.write("Entre ton **code personnel élève**.")
        student_code = st.text_input(
            "Code élève",
            max_chars=4,
            placeholder="Ex. K7P4",
            key="student_code_input",
        )
        if st.button("Continuer", use_container_width=True, key="identify_student"):
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
            if st.button("🏆 Rejoindre le défi", type="primary", use_container_width=True):
                found = find_open_challenge(used_code)
                if not found:
                    st.error("Ce défi n'existe pas ou il est fermé.")
                elif found["class_name"] != student["class_name"]:
                    st.error("Ce défi n'est pas destiné à ta classe.")
                elif attempts_used(student, found) >= int(found["max_attempts"]):
                    st.error("Tu as déjà utilisé toutes les tentatives autorisées.")
                else:
                    st.session_state.active_challenge = found
                    suffix = f"challenge_{found['code']}_{student['id']}"
                    init_game(found["level"], suffix)
                    st.rerun()

        with c2:
            if st.button("Changer d'élève", use_container_width=True):
                st.session_state.pop("challenge_student", None)
                st.query_params.clear()
                st.rerun()
        return

    st.markdown(f"### Défi {challenge['code']} — {challenge['game']}")
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


def teacher_login():
    if st.session_state.get("teacher_authenticated", False):
        return True

    st.subheader("🔒 Connexion professeur")
    password = st.text_input("Mot de passe", type="password", key="teacher_password")

    if st.button("Se connecter", use_container_width=True, key="teacher_login"):
        expected = st.secrets.get("TEACHER_PASSWORD", "")
        if not expected:
            st.error("Le secret TEACHER_PASSWORD n'est pas configuré.")
        elif password == expected:
            st.session_state.teacher_authenticated = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    return False


def page_teacher():
    if not teacher_login():
        return

    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.subheader("👨‍🏫 Espace professeur")
    with top_right:
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.teacher_authenticated = False
            st.rerun()

    tab_classes, tab_students, tab_challenges, tab_results = st.tabs(
        ["🏫 Classes", "👥 Élèves", "🏆 Défis", "📊 Résultats"]
    )

    with tab_classes:
        st.markdown("### Créer une classe")
        class_name = st.text_input("Nom de la classe", placeholder="Ex. 4B")
        if st.button("➕ Ajouter la classe", use_container_width=True):
            if add_class(class_name):
                st.success(f"Classe {class_name.strip().upper()} créée.")
                st.rerun()
            else:
                st.warning("Cette classe existe déjà ou le nom est vide.")

        classes = get_classes()
        st.markdown("### Classes enregistrées")
        if not classes:
            st.info("Aucune classe enregistrée.")
        else:
            cols = st.columns(4)
            for i, item in enumerate(classes):
                with cols[i % 4]:
                    st.markdown(f"### {item}")

    with tab_students:
        classes = get_classes()

        st.markdown("### Importer une base élèves depuis Excel")

        st.write(
            "Le fichier Excel doit contenir au minimum les colonnes "
            "**Prénom**, **Classe** et soit **Nom**, soit **Initiale du nom**. "
            "Si le nom complet est fourni, Ludo n'en conserve que la première lettre."
        )

        template_df = make_student_template()
        template_bytes = template_df.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            "📄 Télécharger un exemple de structure",
            data=template_bytes,
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

                st.markdown("#### Aperçu du fichier")
                st.dataframe(
                    excel_df.head(15),
                    use_container_width=True,
                    hide_index=True,
                )

                first_col, last_col, initial_col, class_col = detect_student_columns(excel_df)

                detected = []
                if first_col:
                    detected.append(f"Prénom → **{first_col}**")
                if last_col:
                    detected.append(f"Nom → **{last_col}**")
                if initial_col:
                    detected.append(f"Initiale → **{initial_col}**")
                if class_col:
                    detected.append(f"Classe → **{class_col}**")

                if detected:
                    st.info("Colonnes détectées : " + " · ".join(detected))

                if st.button(
                    "📥 Importer les élèves dans Ludo",
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
        st.markdown("### Ajouter ponctuellement un élève")

        if not classes:
            st.info(
                "Tu peux importer directement un fichier Excel : "
                "les classes seront créées automatiquement."
            )
        else:
            c1, c2, c3 = st.columns([2, 1, 1])

            with c1:
                first_name = st.text_input(
                    "Prénom",
                    key="new_student_firstname",
                )

            with c2:
                last_initial = st.text_input(
                    "Initiale du nom",
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
                "➕ Ajouter l'élève et générer son code",
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
                        f"Élève ajouté : **{student['first_name']} "
                        f"{student['last_initial']}.** — code personnel "
                        f"**{student['code']}**"
                    )
                    st.rerun()

        students = get_students()

        st.markdown("### Élèves enregistrés")

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
                if (
                    selected_filter == "Toutes"
                    or s["class_name"] == selected_filter
                )
            ]

            st.caption(
                f"{len(filtered)} élève(s) affiché(s) sur {len(students)} enregistré(s)."
            )

            if filtered:
                pdf_cards = generate_student_cards_pdf(
                    filtered,
                    title="Ludo Physique-Chimie",
                )

                if selected_filter == "Toutes":
                    pdf_filename = "cartes_eleves_ludo_toutes_classes.pdf"
                else:
                    pdf_filename = (
                        f"cartes_eleves_ludo_{selected_filter}.pdf"
                    )

                st.download_button(
                    "🖨️ Télécharger les cartes élèves en PDF (code + QR)",
                    data=pdf_cards,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"download_cards_{selected_filter}",
                )

            for student in sorted(
                filtered,
                key=lambda s: (
                    s["class_name"],
                    s["first_name"].lower(),
                    s["last_initial"],
                ),
            ):
                with st.container(border=True):
                    a, b, c = st.columns([2, 1, 1])

                    with a:
                        st.write(
                            f"**{student['first_name']} "
                            f"{student['last_initial']}.**"
                        )

                    with b:
                        st.write(
                            f"Classe **{student['class_name']}**"
                        )

                    with c:
                        st.code(student["code"])

    with tab_challenges:
        classes = get_classes()
        st.markdown("### Créer un nouveau défi")

        if not classes:
            st.warning("Crée d'abord au moins une classe.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                selected_class = st.selectbox("Classe", classes, key="challenge_class")
            with c2:
                challenge_level = st.selectbox(
                    "Niveau",
                    LEVEL_NAMES,
                    key="challenge_level",
                    format_func=lambda x: f"{LEVELS[x]['emoji']} {x}",
                )
            with c3:
                max_attempts = st.selectbox(
                    "Nombre de tentatives", [1, 2, 3], index=0
                )

            if st.button("🏆 Créer le défi", type="primary", use_container_width=True):
                challenge = create_challenge(
                    selected_class, challenge_level, max_attempts
                )
                st.success(
                    f"Défi créé — code **{challenge['code']}** "
                    f"pour la classe **{challenge['class_name']}**."
                )
                st.rerun()

        st.markdown("---")
        st.markdown("### Défis enregistrés")
        challenges = get_challenges()

        if not challenges:
            st.info("Aucun défi enregistré.")
        else:
            for challenge in reversed(challenges):
                status_open = challenge["status"] == "open"
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                    with c1:
                        st.markdown(f"## {challenge['code']}")
                        st.write("🟢 OUVERT" if status_open else "⚫ FERMÉ")
                    with c2:
                        st.write(f"**Classe :** {challenge['class_name']}")
                        st.write(f"**Niveau :** {challenge['level']}")
                    with c3:
                        st.write(f"**Jeu :** {challenge['game']}")
                        st.write(f"**Tentatives :** {challenge['max_attempts']}")
                    with c4:
                        if status_open and st.button(
                            "Fermer",
                            key=f"close_{challenge['code']}",
                            use_container_width=True,
                        ):
                            close_challenge(challenge["code"])
                            st.rerun()

    with tab_results:
        results = get_results()
        st.markdown("### Résultats enregistrés")

        if not results:
            st.info("Aucun résultat pour le moment.")
        else:
            classes = ["Toutes"] + get_classes()
            result_class = st.selectbox(
                "Classe", classes, key="result_class_filter"
            )
            filtered = [
                r for r in results
                if result_class == "Toutes" or r["class_name"] == result_class
            ]
            filtered = sorted(
                filtered,
                key=lambda r: (r["errors"], r["time_seconds"])
            )

            table = []
            for rank, r in enumerate(filtered, start=1):
                table.append({
                    "Rang": rank,
                    "Élève": f"{r['first_name']} {r['last_initial']}.",
                    "Classe": r["class_name"],
                    "Défi": r["challenge_code"],
                    "Niveau": r["level"],
                    "Tentative": r["attempt"],
                    "Erreurs": r["errors"],
                    "Temps": f"{r['time_seconds'] // 60}:{r['time_seconds'] % 60:02d}",
                    "Badge": "🎯 Sans faute" if r["errors"] == 0 else "",
                })

            st.dataframe(table, use_container_width=True, hide_index=True)


st.title("🧪 Ludo Physique-Chimie")

tab_free, tab_challenge, tab_teacher = st.tabs(
    ["🎮 Entraînement libre", "🏆 Participer à un défi", "🔒 Espace professeur"]
)

with tab_free:
    page_free_play()

with tab_challenge:
    page_join_challenge()

with tab_teacher:
    page_teacher()

st.divider()
st.caption(
    "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes "
    "— licence CC BY-NC-SA."
)
