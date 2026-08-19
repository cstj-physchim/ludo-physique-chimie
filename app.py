import random
import time
from pathlib import Path

import streamlit as st
from levels import LEVELS, LEVEL_NAMESimport random
import time
from pathlib import Path

import streamlit as st
from upstash_redis import Redis
from levels import LEVELS, LEVEL_NAMES

redis = Redis(
    url=st.secrets["UPSTASH_REDIS_REST_URL"],
    token=st.secrets["UPSTASH_REDIS_REST_TOKEN"],
)

st.set_page_config(
    page_title="Ludo Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

st.set_page_config(
    page_title="Ludo Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

ASSETS = Path("assets/molecules")


def game_key(level):
    return f"game_{level}"


def init_game(level):
    cfg = LEVELS[level]
    order = cfg["order"]
    start = random.choice(order)
    remaining = [x for x in order if x != start]
    random.shuffle(remaining)

    st.session_state[game_key(level)] = {
        "chain": [start],
        "remaining": remaining,
        "errors": 0,
        "started": time.time(),
    }


def formula_block(formula):
    st.markdown(
        f"""<div style="
        min-height:115px;
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:1.55rem;
        text-align:center;
        font-weight:500;
        ">{formula}</div>""",
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
    pad = "padding-right:4%;" if direction == "right" else "padding-left:4%;"
    arrow = "↘" if direction == "right" else "↙"

    st.markdown(
        f"<div style='text-align:{align};font-size:2rem;{pad}"
        f"margin-top:-.4rem;margin-bottom:-.2rem'>{arrow}</div>",
        unsafe_allow_html=True,
    )


def show_chain_snake(level, chain, per_row=4):
    for row_index, start in enumerate(range(0, len(chain), per_row)):
        row = chain[start:start + per_row]
        cols = st.columns(per_row)
        going_right = row_index % 2 == 0

        if going_right:
            positions = list(range(len(row)))
        else:
            positions = list(reversed(range(per_row - len(row), per_row)))

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


# ---------------------------------------------------------------------
# ÉTAT DU NIVEAU SÉLECTIONNÉ
# ---------------------------------------------------------------------

if "selected_level" not in st.session_state:
    st.session_state.selected_level = LEVEL_NAMES[0]


st.title("🧪 Ludo Physique-Chimie")
st.subheader("🁢 Dominos — Molécules")

# Le selectbox utilise désormais une clé de session.
# Cela permet aux gros boutons de fin de partie de changer le niveau.
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
total = len(LEVELS[level]["order"])

top1, top2, top3 = st.columns([1, 1, 2])

with top1:
    if st.button("🔄 Nouvelle partie", use_container_width=True):
        init_game(level)
        st.rerun()

with top2:
    st.metric("Erreurs", game["errors"])

with top3:
    st.write(
        f"Dominos posés : **{len(game['chain'])} / {total}**"
    )

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
                    key=f"{level}_{did}",
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
        st.metric("Temps", f"{elapsed // 60} min {elapsed % 60:02d} s")
    with r3:
        st.metric("Dominos", f"{total}/{total}")

    if game["errors"] == 0:
        st.success("🎯 Badge obtenu : Sans faute")

    current_index = LEVEL_NAMES.index(level)

    st.markdown("### Que veux-tu faire maintenant ?")

    # Deux gros boutons côte à côte.
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
            next_level = LEVEL_NAMES[current_index + 1]

            if st.button(
                f"➡️ Passer au niveau suivant : {LEVELS[next_level]['emoji']} {next_level}",
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

st.divider()
st.caption(
    "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes — licence CC BY-NC-SA."
)
