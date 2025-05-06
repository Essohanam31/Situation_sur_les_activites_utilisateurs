# NOTE: Ce script nécessite que le module 'streamlit' soit installé dans votre environnement Python.
# Installez-le avec : pip install streamlit

import streamlit as st
import pandas as pd
import requests
import base64
from datetime import datetime, timedelta

st.set_page_config(page_title="DHIS2 - Doublons & Audit", layout="wide")

# URL DHIS2 fixe corrigée
dhis2_url = "https://togo.dhis2.org/dhis"

# Onglet Connexion
st.sidebar.header("🔐 Connexion à DHIS2")
username = st.sidebar.text_input("Nom d'utilisateur", type="default")
password = st.sidebar.text_input("Mot de passe", type="password")

# Authentification de base
@st.cache_data(show_spinner=False)
def get_auth_header(username, password):
    token = f"{username}:{password}"
    encoded = base64.b64encode(token.encode()).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}

# Obtenir les unités d'organisation
@st.cache_data(show_spinner=False)
def get_organisation_units(base_url, headers):
    url = f"{base_url}/api/organisationUnits.json"
    params = {"paging": "false", "fields": "id,name,level,parent[id]"}
    r = requests.get(url, headers=headers, params=params)
    try:
        r.raise_for_status()
        data = r.json()
        return data.get("organisationUnits", [])
    except Exception as e:
        st.error(f"Erreur lors de la récupération des unités d'organisation : {e}")
        return []

# Obtenir les utilisateurs
@st.cache_data(show_spinner=False)
def get_all_users(base_url, headers):
    url = f"{base_url}/api/users.json"
    params = {
        "paging": "false",
        "fields": "id,username,name,organisationUnits[id]"
    }
    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        st.error("Erreur lors de la récupération des utilisateurs.")
        return []
    return r.json().get("users", [])

# Obtenir les connexions des utilisateurs (audit)
@st.cache_data(show_spinner=False)
def get_user_logins(base_url, headers):
    url = f"{base_url}/api/userCredentials?fields=username,lastLogin&paging=false"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get("userCredentials", [])
    else:
        return []

if username and password:
    headers = get_auth_header(username, password)

    st.sidebar.subheader("🏥 Sélection de l'unité d'organisation")
    units = get_organisation_units(dhis2_url, headers)
    unit_options = {unit['name']: unit['id'] for unit in units}

    if unit_options:
        selected_name = st.sidebar.selectbox("Choisir une unité", list(unit_options.keys()))
        selected_id = unit_options[selected_name]

        if st.sidebar.button("📥 Charger les utilisateurs"):
            st.info(f"Chargement des utilisateurs pour l'unité : {selected_name}")
            users = get_all_users(dhis2_url, headers)

            filtered_users = []
            for user in users:
                for ou in user.get("organisationUnits", []):
                    if ou['id'] == selected_id:
                        filtered_users.append(user)
                        break

            if filtered_users:
                df_users = pd.DataFrame(filtered_users)
                df_users = df_users[['id', 'username', 'name']]
                df_users['doublon'] = df_users.duplicated(subset='name', keep=False)
                df_users['doublon'] = df_users['doublon'].apply(lambda x: "Oui" if x else "Non")

                st.success(f"✅ {len(df_users)} utilisateurs trouvés.")
                st.dataframe(df_users, use_container_width=True)

                csv = df_users.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📄 Télécharger la liste CSV",
                    data=csv,
                    file_name="utilisateurs_dhis2.csv",
                    mime='text/csv'
                )
            else:
                st.warning("Aucun utilisateur trouvé pour cette unité.")

    st.sidebar.subheader("📊 Période d'analyse des connexions")
    start_date = st.sidebar.date_input("Début", datetime.today() - timedelta(days=30))
    end_date = st.sidebar.date_input("Fin", datetime.today())

    if start_date > end_date:
        st.sidebar.error("La date de début doit être antérieure à la date de fin.")
    elif st.sidebar.button("📈 Analyser l'activité"):
        st.subheader("🔍 Audit d'activité des utilisateurs DHIS2")
        data = get_user_logins(dhis2_url, headers)
        df = pd.DataFrame(data)

        if "lastLogin" in df.columns:
            df['lastLogin'] = pd.to_datetime(df['lastLogin'], errors='coerce')

            df['Actif durant la période'] = df['lastLogin'].apply(
                lambda x: "Oui" if pd.notnull(x) and start_date <= x.date() <= end_date else "Non"
            )

            st.dataframe(df.sort_values("lastLogin", ascending=False), use_container_width=True)

            filtered = df[df["Actif durant la période"] == "Oui"]
            if not filtered.empty:
                excel_data = filtered.to_excel(index=False, engine='openpyxl')
                st.download_button(
                    "📤 Exporter les actifs (Excel)",
                    data=excel_data,
                    file_name="utilisateurs_actifs.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("Aucun utilisateur actif trouvé durant la période.")
        else:
            st.warning("Aucune donnée de connexion trouvée.")

    # Export complet depuis le niveau 5
    if st.sidebar.button("📦 Export utilisateurs du niveau 5 et plus"):
        st.subheader("📋 Export des utilisateurs (niveaux ≥ 5, regroupés par niveau)")
        all_units = get_organisation_units(dhis2_url, headers)
        all_users = get_all_users(dhis2_url, headers)

        unit_dict = {u['id']: u for u in all_units}
        level_map = {lvl: {} for lvl in range(5, 1-1, -1)}  # niveaux de 5 à 1

        for user in all_users:
            for ou in user.get('organisationUnits', []):
                ou_id = ou['id']
                current = unit_dict.get(ou_id)

                while current and current['level'] >= 5:
                    lvl = current['level']
                    if current['id'] not in level_map[lvl]:
                        level_map[lvl][current['id']] = {
                            'name': current['name'],
                            'users': []
                        }
                    level_map[lvl][current['id']]['users'].append({
                        "Nom complet": user.get("name"),
                        "Nom d'utilisateur": user.get("username"),
                        "ID utilisateur": user.get("id"),
                        "Unité initiale": ou_id
                    })
                    parent_id = current.get('parent', {}).get('id')
                    current = unit_dict.get(parent_id)

        with pd.ExcelWriter("export_utilisateurs_niveaux.xlsx", engine='openpyxl') as writer:
            for lvl in sorted(level_map.keys()):
                for uid, info in level_map[lvl].items():
                    if info['users']:
                        df = pd.DataFrame(info['users'])
                        nom_feuille = f"N{lvl}_{info['name'][:25]}"
                        df.to_excel(writer, sheet_name=nom_feuille, index=False)

        with open("export_utilisateurs_niveaux.xlsx", "rb") as f:
            st.download_button(
                label="📥 Télécharger l'export utilisateurs par niveau",
                data=f.read(),
                file_name="utilisateurs_par_niveau.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
else:
    st.warning("Veuillez renseigner vos identifiants DHIS2 pour commencer.")
