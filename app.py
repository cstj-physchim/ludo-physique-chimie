import random
import time
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Ludo Physique-Chimie", page_icon="🧪", layout="wide")
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

# La correspondance correcte est circulaire : l'image de chaque domino
# correspond à la formule placée à droite du domino précédent.
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
    _, image_name, formula = BY_ID[domino_id]
    with st.container(border=True):
        c1, c2 = st.columns(2, vertical_alignment="center")
        with c1:
            st.image(str(ASSETS / f"{image_name}.svg"), use_container_width=True)
        with c2:
            st.markdown(f"<div style='font-size:2rem;text-align:center'>{formula}</div>", unsafe_allow_html=True)
        if clickable:
            return st.button("Placer ce domino", key=key, use_container_width=True)
    return False

st.title("🧪 Ludo Physique-Chimie")
st.subheader("Dominos — Molécules · Niveau facile")

st.write("Observe la formule située à droite du dernier domino posé et choisis, parmi tes cartes, celle dont le modèle correspond.")

if "chain" not in st.session_state:
    init_game()

if st.button("🔄 Nouvelle partie"):
    init_game()
    st.rerun()

st.markdown("### Chaîne construite")
cols = st.columns(min(4, len(st.session_state.chain)))
for i, did in enumerate(st.session_state.chain[-4:]):
    with cols[i]:
        show_domino(did)

if st.session_state.remaining:
    st.markdown("### Dominos disponibles")
    expected = next_expected()
    cols = st.columns(3)
    clicked = None
    for i, did in enumerate(st.session_state.remaining):
        with cols[i % 3]:
            if show_domino(did, key=f"pick_{did}", clickable=True):
                clicked = did
    if clicked:
        if clicked == expected:
            st.session_state.chain.append(clicked)
            st.session_state.remaining.remove(clicked)
            st.rerun()
        else:
            st.session_state.errors += 1
            st.error("Ce domino ne correspond pas. Observe à nouveau le modèle et la formule.")
else:
    elapsed = int(time.time() - st.session_state.started)
    st.success(f"🎉 Chaîne terminée ! Erreurs : {st.session_state.errors} · Temps : {elapsed//60} min {elapsed%60:02d} s")

st.divider()
st.caption("Adaptation numérique du jeu de Stéphane Bois et Hervé Abbes — CC BY-NC-SA.")
