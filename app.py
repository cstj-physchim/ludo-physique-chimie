import streamlit as st

st.set_page_config(
    page_title="Ludo Physique-Chimie",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Ludo Physique-Chimie")
st.subheader("Apprendre et réviser en jouant")

st.write(
    """
    Choisis un jeu de dominos. Les trois premières versions utiliseront
    le même moteur de jeu, avec des contenus différents.
    """
)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 🧪 Molécules")
    st.write("Associer noms, formules et représentations moléculaires.")
    if st.button("Jouer — Molécules", use_container_width=True):
        st.session_state["jeu"] = "Molécules"

with col2:
    st.markdown("### ⚡ Électricité")
    st.write("Associer composants électriques et symboles normalisés.")
    if st.button("Jouer — Électricité", use_container_width=True):
        st.session_state["jeu"] = "Électricité"

with col3:
    st.markdown("### ⚛️ Ions")
    st.write("Associer noms des ions et formules ioniques.")
    if st.button("Jouer — Ions", use_container_width=True):
        st.session_state["jeu"] = "Ions"

if "jeu" in st.session_state:
    st.divider()
    st.success(f"Jeu sélectionné : {st.session_state['jeu']}")
    st.info(
        "Pour l'instant, cette première version vérifie uniquement "
        "l'écran d'accueil. Le moteur de dominos sera ajouté à l'étape suivante."
    )

st.divider()
st.caption("Ludo Physique-Chimie — Collège Saint-Jacques")
