import random
import time
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Ludo Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

ASSETS = Path("assets/molecules")

DOMINOS = [
    ("A1", "h2", "O₂"),
    ("A6", "o2", "2 C"),
    ("A11", "2c", "CH₄"),
    ("A10", "ch4", "N₂"),
    ("A8", "n2", "2 H"),
    ("A9", "2h", "H₂O"),
    ("A12", "h2o", "CO₂"),
    ("A7", "co2", "C + O₂"),
    ("A3", "c_plus_o2", "N + O₂"),
    ("A14", "n_plus_o2", "H₂ + O"),
    ("A2", "h2_plus_o", "CO"),
    ("A13", "co", "NO₂"),
    ("A5", "no2", "2 N"),
    ("A4", "2n", "H₂"),
]

ORDER = [d[0] for d in DOMINOS]
BY_ID = {d[0]: d for d in DOMINOS}


def init_game():
    start = random.choice(ORDER)
    remaining = [x for x in ORDER if x != start]
    random.shuffle(remaining)

    st.session_state.chain = [start]
    st.session_state.remaining = remaining
    st.session_state.errors = 0
    st.session_state.started = time.time()


def next_expected():
    current = st.session_state.chain[-1]
    i = ORDER.index(current)
    return ORDER[(i + 1) % len(ORDER)]


def formula_block(formula):
    st.markdown(
        f"""
        <div style="
            min-height:115px;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:1.7rem;
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
        width=115,
    )


def show_domino(domino_id, key=None, clickable=False, reversed_domino=False):
    """
    Affiche un domino de taille constante.

    reversed_domino=False : [ modèle | formule ]
    reversed_domino=True  : [ formule | modèle ]

    On inverse donc réellement les deux moitiés quand la chaîne repart
    de droite vers la gauche, comme avec de vrais dominos.
    """
    _, image_name, formula = BY_ID[domino_id]

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
    """Indique visuellement le virage de la chaîne."""
    if direction == "right":
        st.markdown(
            """
            <div style="
                text-align:right;
                font-size:2rem;
                padding-right:4%;
                margin-top:-0.4rem;
                margin-bottom:-0.2rem;
            ">↘</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="
                text-align:left;
                font-size:2rem;
                padding-left:4%;
                margin-top:-0.4rem;
                margin-bottom:-0.2rem;
            ">↙</div>
            """,
            unsafe_allow_html=True,
        )


def show_chain_snake(chain, per_row=4):
    """
    Affiche toute la chaîne comme un vrai serpent :

    ligne 1 :  [modèle|formule] → [modèle|formule] → ...
    ligne 2 :  ... ← [formule|modèle] ← [formule|modèle]
    ligne 3 :  [modèle|formule] → [modèle|formule] → ...

    Les dominos de chaque ligne allant vers la gauche sont donc retournés.
    """
    for row_index, start in enumerate(range(0, len(chain), per_row)):
        row = chain[start:start + per_row]
        cols = st.columns(per_row)

        going_right = row_index % 2 == 0

        if going_right:
            # Le premier domino de la ligne se place à gauche,
            # puis les suivants avancent vers la droite.
            positions = list(range(len(row)))
        else:
            # Le premier domino de la ligne se place à droite,
            # puis les suivants avancent vers la gauche.
            positions = list(reversed(range(per_row - len(row), per_row)))

        for domino_id, col_index in zip(row, positions):
            with cols[col_index]:
                show_domino(
                    domino_id,
                    reversed_domino=not going_right,
                )

        # Virage uniquement s'il existe déjà au moins un domino
        # sur la ligne suivante.
        if start + per_row < len(chain):
            show_turn("right" if going_right else "left")


st.title("🧪 Ludo Physique-Chimie")
st.subheader("Dominos — Molécules · Niveau facile")

st.write(
    "Observe l'extrémité libre du dernier domino posé et choisis, "
    "parmi tes cartes, celle dont le modèle correspond."
)

if "chain" not in st.session_state:
    init_game()

top1, top2, top3 = st.columns([1, 1, 2])

with top1:
    if st.button("🔄 Nouvelle partie", use_container_width=True):
        init_game()
        st.rerun()

with top2:
    st.metric("Erreurs", st.session_state.errors)

with top3:
    st.write(
        f"Dominos posés : **{len(st.session_state.chain)} / {len(DOMINOS)}**"
    )

st.markdown("### Chaîne construite")

show_chain_snake(st.session_state.chain, per_row=4)

if st.session_state.remaining:
    st.markdown("### Dominos disponibles")

    expected = next_expected()
    clicked = None

    # Les cartes de la réserve restent toujours dans leur orientation d'origine.
    for row_start in range(0, len(st.session_state.remaining), 3):
        row = st.session_state.remaining[row_start:row_start + 3]
        cols = st.columns(3)

        for i, did in enumerate(row):
            with cols[i]:
                if show_domino(
                    did,
                    key=f"pick_{did}",
                    clickable=True,
                    reversed_domino=False,
                ):
                    clicked = did

    if clicked:
        if clicked == expected:
            st.session_state.chain.append(clicked)
            st.session_state.remaining.remove(clicked)
            st.rerun()
        else:
            st.session_state.errors += 1
            st.error(
                "Ce domino ne correspond pas. "
                "Observe à nouveau l'extrémité de la chaîne."
            )

else:
    elapsed = int(time.time() - st.session_state.started)

    st.success(
        f"🎉 Chaîne terminée ! "
        f"Erreurs : {st.session_state.errors} · "
        f"Temps : {elapsed // 60} min {elapsed % 60:02d} s"
    )

st.divider()
st.caption(
    "Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes — CC BY-NC-SA."
)
