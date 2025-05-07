import streamlit as st
import pandas as pd
import requests
from collections import defaultdict

st.set_page_config(page_title="🧭 Rapport Utilisateurs DHIS2", layout="wide")
st.title("📊 Rapport des Utilisateurs DHIS2 par Niveau d'Organisation")

# --- Connexion DHIS2 ---
st.sidebar.header("🔐 Connexion DHIS2")
dhis2_url = "https://togo.dhis2.org/dhis"
pat = st.sidebar.text_input("Token d'accès personnel (PAT)", type="password")

headers = {"Authorization": f"ApiToken {pat}"}

# --- Récupération des unités d'organisation ---
@st.cache_data(ttl=3600)
def get_org_units():
    units = []
    url = f"{dhis2_url}/api/organisationUnits?paging=false&fields=id,name,level,parent[id],path"
    res = requests.get(url, headers=headers)
    if res.ok:
        units = res.json()["organisationUnits"]
    return pd.DataFrame(units)

# --- Récupération des utilisateurs ---
@st.cache_data(ttl=3600)
def get_users():
    users = []
    url = f"{dhis2_url}/api/users?paging=false&fields=id,username,name,organisationUnits[id,name,path]"
    res = requests.get(url, headers=headers)
    if res.ok:
        users = res.json()["users"]
    return users

if pat:
    with st.spinner("🔄 Chargement des données..."):
        org_df = get_org_units()
        user_data = get_users()

        # Préparer les utilisateurs avec leurs unités
        records = []
        for user in user_data:
            for ou in user.get("organisationUnits", []):
                records.append({
                    "user_id": user["id"],
                    "username": user.get("username", ""),
                    "name": user.get("name", ""),
                    "orgunit_id": ou["id"],
                    "orgunit_name": ou["name"],
                    "path": ou["path"]
                })
        df_users = pd.DataFrame(records)

        # Lier avec les niveaux et noms hiérarchiques
        org_df = org_df.rename(columns={"id": "orgunit_id", "name": "orgunit_name"})
        df = pd.merge(df_users, org_df[["orgunit_id", "level"]], on="orgunit_id", how="left")

        # Doublons par nom
        duplicated_names = df["name"].duplicated(keep=False)
        df["doublon"] = duplicated_names

        # Extraire hiérarchie par niveau depuis le path
        def extract_level(path, level):
            parts = path.strip("/").split("/")
            return parts[level - 1] if len(parts) >= level else None

        for lvl in range(1, 7):
            df[f"level_{lvl}_id"] = df["path"].apply(lambda x: extract_level(x, lvl))

        # Associer noms des niveaux supérieurs
        for lvl in range(1, 7):
            mapping = org_df[org_df["level"] == lvl].set_index("orgunit_id")["orgunit_name"].to_dict()
            df[f"level_{lvl}_name"] = df[f"level_{lvl}_id"].map(mapping)

        # Filtrage par région/district
        st.sidebar.header("🔍 Filtres")
        selected_regions = st.sidebar.multiselect("Filtrer par Région", options=df["level_2_name"].dropna().unique())
        selected_districts = st.sidebar.multiselect("Filtrer par District", options=df["level_3_name"].dropna().unique())

        if selected_regions:
            df = df[df["level_2_name"].isin(selected_regions)]
        if selected_districts:
            df = df[df["level_3_name"].isin(selected_districts)]

        # Agrégation pour le tableau croisé dynamique
        grouped = df.groupby(["level_2_name", "level_3_name", "level_4_name", "level_5_name"]).agg(
            total_utilisateurs=("username", "count"),
            doublons=("doublon", "sum")
        ).reset_index()
        grouped["% Doublons"] = round((grouped["doublons"] / grouped["total_utilisateurs"]) * 100, 1)

        st.success(f"{len(df)} utilisateurs chargés.")
        st.dataframe(grouped, use_container_width=True)

        # Export
        csv = grouped.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Télécharger le rapport", csv, "rapport_utilisateurs_dhis2.csv", "text/csv")
else:
    st.info("Veuillez entrer le token personnel d'accès (PAT) pour continuer.")
