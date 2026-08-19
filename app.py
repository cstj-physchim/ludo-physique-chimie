import json
import random
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from upstash_redis import Redis
from levels import LEVELS, LEVEL_NAMES

st.set_page_config(
    page_title="Ludo Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

ASSETS = Path("assets/molecules")

# ---------------------------------------------------------------------
# CONNEXION UPSTASH
# ---------------------------------------------------------------------

redis = Redis(
    url=st.secrets["UPSTASH_REDIS_REST_URL"],
    token=st.secrets["UPSTASH_REDIS_REST_TOKEN"],
)

CLASSES_KEY = "ludo:classes"
CHALLENGES_KEY = "ludo:challenges"


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


# ---------------------------------------------------------------------
# DONNÉES PROFESSEUR
# ---------------------------------------------------------------------

def get_classes():
    classes = redis_read_json(CLASSES_KEY, [])
    return sorted(set(classes))


def add_class(class_name):
    class_name = class_name.strip().upper()
    if not class_name:
        return False

    classes = get_classes()

    if class_name not in classes:
        classes.append(class_name)
        redis_write_json(CLASSES_KEY, sorted(classes))
        return True

    return False


def get_challenges():
    challenges = redis_read_json(CHALLENGES_KEY, [])
    return challenges


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

    code = generate_challenge_code()

    challenge = {
        "code": code,
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


# ---------------------------------------------------------------------
# MOTEUR DOMINOS
# ---------------------------------------------------------------------

def game_key(level):
    return f"game_{level}"


def init_game(level):
    cfg = LEVELS[level]
    order = cfg["order"]

    start = random.choice(order)

    remaining = [
        domino_id
        for domino_id in order
        if domino_id != start
    ]

    random.shuffle(remaining)

    st.session_state[game_key(level)] = {
        "chain": [start],
        "remaining": remaining,
        "errors": 0,
        "started": time.time(),
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


def show_domino(
    level,
    domino_id,
    key=None,
    clickable=False,
    reversed_domino=False,
):
    image_name, formula = LEVELS[level]["dominos"][domino_id]

    with st.container(border=True):

        left, right = st.columns(
            [1, 1],
            vertical_alignment="center",
        )

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
        "padding-right:4%;"
        if direction == "right"
        else "padding-left:4%;"
    )
    arrow = "↘" if direction == "right" else "↙"

    st.markdown(
        f"""
        <div style="
            text-align:{align};
            font-size:2rem;
            {pad}
            margin-top:-0.4rem;
            margin-bottom:-0.2rem;
        ">
            {arrow}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_chain_snake(level, chain, per_row=4):

    for row_index, start in enumerate(
        range(0, len(chain), per_row)
    ):

        row = chain[start:start + per_row]

        cols = st.columns(per_row)

        going_right = row_index % 2 == 0

        if going_right:

            positions = list(range(len(row)))

        else:

            positions = list(
                reversed(
                    range(
                        per_row - len(row),
                        per_row,
                    )
                )
            )

        for domino_id, col_index in zip(
            row,
            positions,
        ):

            with cols[col_index]:

                show_domino(
                    level,
                    domino_id,
                    reversed_domino=not going_right,
                )

        if start + per_row < len(chain):

            show_turn(
                "right"
                if going_right
                else "left"
            )


def next_expected(level, chain):

    order = LEVELS[level]["order"]

    i = order.index(chain[-1])

    return order[
        (i + 1) % len(order)
    ]


# ---------------------------------------------------------------------
# PAGE JEU
# ---------------------------------------------------------------------

def page_game():

    st.subheader("🁢 Dominos — Molécules")

    if "selected_level" not in st.session_state:
        st.session_state.selected_level = LEVEL_NAMES[0]

    level = st.selectbox(
        "Choisis ton niveau",
        LEVEL_NAMES,
        key="selected_level",
        format_func=lambda x: f"{LEVELS[x]['emoji']} {x}",
    )

    key = game_key(level)

    if key not in st.session_state:
        init_game(level)

    game = st.session_state[key]

    total = len(
        LEVELS[level]["order"]
    )

    top1, top2, top3 = st.columns(
        [1, 1, 2]
    )

    with top1:

        if st.button(
            "🔄 Nouvelle partie",
            use_container_width=True,
        ):

            init_game(level)
            st.rerun()

    with top2:

        st.metric(
            "Erreurs",
            game["errors"],
        )

    with top3:

        st.write(
            f"Dominos posés : "
            f"**{len(game['chain'])} / {total}**"
        )

    st.info(
        "Observe l'extrémité libre du dernier domino posé "
        "et choisis, parmi tes cartes, celle dont le modèle correspond."
    )

    st.markdown(
        "### Chaîne construite"
    )

    show_chain_snake(
        level,
        game["chain"],
        per_row=4,
    )

    if game["remaining"]:

        st.markdown(
            "### Dominos disponibles"
        )

        expected = next_expected(
            level,
            game["chain"],
        )

        clicked = None

        for row_start in range(
            0,
            len(game["remaining"]),
            3,
        ):

            row = game["remaining"][
                row_start:row_start + 3
            ]

            cols = st.columns(3)

            for i, did in enumerate(row):

                with cols[i]:

                    if show_domino(
                        level,
                        did,
                        key=f"{level}_{did}",
                        clickable=True,
                        reversed_domino=False,
                    ):

                        clicked = did

        if clicked:

            if clicked == expected:

                game["chain"].append(
                    clicked
                )

                game["remaining"].remove(
                    clicked
                )

                st.rerun()

            else:

                game["errors"] += 1

                st.error(
                    "Ce domino ne correspond pas. "
                    "Observe à nouveau l'extrémité de la chaîne."
                )

    else:

        elapsed = int(
            time.time()
            - game["started"]
        )

        st.markdown("---")
        st.markdown(
            "## 🎉 Niveau terminé !"
        )

        r1, r2, r3 = st.columns(3)

        with r1:
            st.metric(
                "Erreurs",
                game["errors"],
            )

        with r2:
            st.metric(
                "Temps",
                f"{elapsed // 60} min "
                f"{elapsed % 60:02d} s",
            )

        with r3:
            st.metric(
                "Dominos",
                f"{total}/{total}",
            )

        if game["errors"] == 0:

            st.success(
                "🎯 Badge obtenu : Sans faute"
            )

        current_index = LEVEL_NAMES.index(
            level
        )

        st.markdown(
            "### Que veux-tu faire maintenant ?"
        )

        left, right = st.columns(2)

        with left:

            if st.button(
                "🔄 Rejouer le même niveau",
                key=f"replay_{level}",
                type="secondary",
                use_container_width=True,
            ):

                init_game(level)

                st.rerun()

        with right:

            if current_index < len(LEVEL_NAMES) - 1:

                next_level = LEVEL_NAMES[
                    current_index + 1
                ]

                if st.button(
                    f"➡️ Passer au niveau suivant : "
                    f"{LEVELS[next_level]['emoji']} "
                    f"{next_level}",
                    key=f"next_{level}",
                    type="primary",
                    use_container_width=True,
                ):

                    st.session_state.selected_level = next_level

                    init_game(next_level)

                    st.rerun()

            else:

                if st.button(
                    "🏆 Recommencer depuis le niveau Facile",
                    key="restart_all",
                    type="primary",
                    use_container_width=True,
                ):

                    first_level = LEVEL_NAMES[0]

                    st.session_state.selected_level = first_level

                    init_game(first_level)

                    st.rerun()


# ---------------------------------------------------------------------
# ESPACE PROFESSEUR
# ---------------------------------------------------------------------

def teacher_login():

    if st.session_state.get(
        "teacher_authenticated",
        False,
    ):
        return True

    st.subheader(
        "🔒 Connexion professeur"
    )

    password = st.text_input(
        "Mot de passe",
        type="password",
    )

    if st.button(
        "Se connecter",
        use_container_width=True,
    ):

        expected_password = st.secrets.get(
            "TEACHER_PASSWORD",
            "",
        )

        if not expected_password:

            st.error(
                "Le secret TEACHER_PASSWORD n'est pas encore configuré dans Streamlit."
            )

            return False

        if password == expected_password:

            st.session_state.teacher_authenticated = True

            st.rerun()

        else:

            st.error(
                "Mot de passe incorrect."
            )

    return False


def page_teacher():

    if not teacher_login():
        return

    top_left, top_right = st.columns(
        [4, 1]
    )

    with top_left:

        st.subheader(
            "👨‍🏫 Espace professeur"
        )

    with top_right:

        if st.button(
            "Déconnexion",
            use_container_width=True,
        ):

            st.session_state.teacher_authenticated = False

            st.rerun()

    tab_classes, tab_challenges = st.tabs(
        [
            "🏫 Classes",
            "🏆 Défis",
        ]
    )

    # ---------------------------------------------------------------
    # CLASSES
    # ---------------------------------------------------------------

    with tab_classes:

        st.markdown(
            "### Créer une classe"
        )

        class_name = st.text_input(
            "Nom de la classe",
            placeholder="Ex. 4B",
        )

        if st.button(
            "➕ Ajouter la classe",
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

        st.markdown(
            "### Classes enregistrées"
        )

        if not classes:

            st.info(
                "Aucune classe enregistrée pour le moment."
            )

        else:

            cols = st.columns(4)

            for i, class_item in enumerate(classes):

                with cols[i % 4]:

                    st.markdown(
                        f"### {class_item}"
                    )

    # ---------------------------------------------------------------
    # DÉFIS
    # ---------------------------------------------------------------

    with tab_challenges:

        classes = get_classes()

        st.markdown(
            "### Créer un nouveau défi"
        )

        if not classes:

            st.warning(
                "Crée d'abord au moins une classe."
            )

        else:

            c1, c2, c3 = st.columns(3)

            with c1:

                selected_class = st.selectbox(
                    "Classe",
                    classes,
                    key="challenge_class",
                )

            with c2:

                challenge_level = st.selectbox(
                    "Niveau",
                    LEVEL_NAMES,
                    key="challenge_level",
                    format_func=lambda x: (
                        f"{LEVELS[x]['emoji']} {x}"
                    ),
                )

            with c3:

                max_attempts = st.selectbox(
                    "Nombre de tentatives",
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
                    challenge_level,
                    max_attempts,
                )

                st.success(
                    "Défi créé avec succès."
                )

                st.markdown(
                    f"""
                    ## Code du défi : **{challenge['code']}**

                    **Classe :** {challenge['class_name']}  
                    **Jeu :** {challenge['game']}  
                    **Niveau :** {challenge['level']}  
                    **Tentatives autorisées :** {challenge['max_attempts']}
                    """
                )

        st.markdown("---")
        st.markdown(
            "### Défis enregistrés"
        )

        challenges = get_challenges()

        if not challenges:

            st.info(
                "Aucun défi n'a encore été créé."
            )

        else:

            # Les plus récents en premier
            for challenge in reversed(challenges):

                status_open = (
                    challenge["status"] == "open"
                )

                status_label = (
                    "🟢 OUVERT"
                    if status_open
                    else "⚫ FERMÉ"
                )

                with st.container(border=True):

                    c1, c2, c3, c4 = st.columns(
                        [1, 2, 2, 1]
                    )

                    with c1:

                        st.markdown(
                            f"## {challenge['code']}"
                        )

                        st.write(
                            status_label
                        )

                    with c2:

                        st.write(
                            f"**Classe :** "
                            f"{challenge['class_name']}"
                        )

                        st.write(
                            f"**Niveau :** "
                            f"{challenge['level']}"
                        )

                    with c3:

                        st.write(
                            f"**Jeu :** "
                            f"{challenge['game']}"
                        )

                        st.write(
                            f"**Tentatives :** "
                            f"{challenge['max_attempts']}"
                        )

                    with c4:

                        if status_open:

                            if st.button(
                                "Fermer",
                                key=f"close_{challenge['code']}",
                                use_container_width=True,
                            ):

                                close_challenge(
                                    challenge["code"]
                                )

                                st.rerun()


# ---------------------------------------------------------------------
# NAVIGATION PRINCIPALE
# ---------------------------------------------------------------------

st.title(
    "🧪 Ludo Physique-Chimie"
)

main_tab_game, main_tab_teacher = st.tabs(
    [
        "🎮 Jouer",
        "🔒 Espace professeur",
    ]
)

with main_tab_game:

    page_game()

with main_tab_teacher:

    page_teacher()


st.divider()

st.caption(
    "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes "
    "— licence CC BY-NC-SA."
)
