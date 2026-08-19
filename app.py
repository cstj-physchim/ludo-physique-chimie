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


def show_domino(domino_id, key=None, clickable=False):
    """Affiche un domino toujours dans une case de largeur identique."""
    _, image_name, formula = BY_ID[domino_id]

    with st.container(border=True):
        c1, c2 = st.columns([1, 1], vertical_alignment="center")

        with c1:
            # largeur fixe pour éviter que le premier domino soit gigantesque
            st.image(
                str(ASSETS / f"{image_name}.svg"),
                width=115,
            )

        with c2:
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

        if clickable:
            return st.button(
                "Placer",
                key=key,
                use_container_width=True,
            )

    return False


def show_chain_snake(chain, per_row=4):
    """
    Affiche toute la chaîne.
    Ligne 1 : gauche -> droite
    Ligne 2 : droite -> gauche
    Ligne 3 : gauche -> droite
    etc.
    """
    for row_index, start in enumerate(range(0, len(chain), per_row)):
        row = chain[start:start + per_row]

        # On crée TOUJOURS 4 colonnes, même lorsqu'il n'y a qu'un domino.
        # Ainsi les cartes gardent la même taille du début à la fin.
        cols = st.columns(per_row)

        if row_index % 2 == 0:
            # ligne normale
            positions = list(range(len(row)))
        else:
            # ligne inversée : effet serpent
            positions = list(reversed(range(per_row - len(row), per_row)))

        for domino_id, col_index in zip(row, positions):
            with cols[col_index]:
                show_domino(domino_id)

        # petit indicateur visuel du virage du serpent
        if start + per_row < len(chain):
            if row_index % 2 == 0:
                st.markdown(
                    "<div style='text-align:right;font-size:1.8rem;padding-right:4%;'>↘</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='text-align:left;font-size:1.8rem;padding-left:4%;'>↙</div>",
                    unsafe_allow_html=True,
                )


st.title("🧪 Ludo Physique-Chimie")
st.subheader("Dominos — Molécules · Niveau facile")

st.write(
    "Observe la formule située à droite du dernier domino posé et choisis, "
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
    st.write(f"Dominos posés : **{len(st.session_state.chain)} / {len(DOMINOS)}**")

st.markdown("### Chaîne construite")

# Toute la chaîne reste visible, en serpent.
show_chain_snake(st.session_state.chain, per_row=4)

if st.session_state.remaining:
    st.markdown("### Dominos disponibles")

    expected = next_expected()
    clicked = None

    # 3 cartes par ligne pour garder une bonne lisibilité des choix
    for row_start in range(0, len(st.session_state.remaining), 3):
        row = st.session_state.remaining[row_start:row_start + 3]
        cols = st.columns(3)

        for i, did in enumerate(row):
            with cols[i]:
                if show_domino(did, key=f"pick_{did}", clickable=True):
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
                "Observe à nouveau le modèle et la formule."
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
