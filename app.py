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

# Obtenir les descendants d'une unité d'organisation
@st.cache_data(show_spinner=False)
def get_descendants(base_url, headers, org_unit_id):
    url = f"{base_url}/api/organisationUnits/{org_unit_id}.json?fields=descendants[id]"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        data = r.json()
        return [org_unit_id] + [ou['id'] for ou in data.get('descendants', [])]
    else:
        st.error("Erreur lors de la récupération des descendants de l'unité d'organisation.")
        return [org_unit_id]

# Obtenir les unités d'organisation
@st.cache_data(show_spinner=False)
def get_organisation_units(base_url, headers):
    url = f"{base_url}/api/organisationUnits.json"
    params = {"paging": "false", "fields": "id,name"}
    r = requests.get(url, headers=headers, params=params)
    try:
        r.raise_for_status()
        data = r.json()
        return data.get("organisationUnits", [])
    except Exception as e:
        st.error(f"Erreur lors de la récupération des unités d'organisation : {e}")
        return []

# Obtenir les utilisateurs
def get_users(base_url, headers):
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

        if st.sidebar.button("📅 Charger les utilisateurs"):
            st.info(f"Chargement des utilisateurs pour l'unité : {selected_name}")
            all_users = get_users(dhis2_url, headers)
            descendant_ids = get_descendants(dhis2_url, headers, selected_id)

            filtered = []
            seen = set()
            for user in all_users:
                user_ous = [ou['id'] for ou in user.get('organisationUnits', [])]
                if any(ou in descendant_ids for ou in user_ous):
                    if user['id'] not in seen:
                        filtered.append(user)
                        seen.add(user['id'])

            if filtered:
                df_users = pd.DataFrame(filtered)
                df_users = df_users[['id', 'username', 'name']]

                # Marquer les doublons
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

    # Partie Audit
    st.sidebar.subheader("📊 Période d'analyse des connexions")
    start_date = st.sidebar.date_input("Début", datetime.today() - timedelta(days=30))
    end_date = st.sidebar.date_input("Fin", datetime.today())

    if start_date > end_date:
        st.sidebar.error("La date de début doit être antérieure à la date de fin.")
    elif st.sidebar.button("📈 Analyser l'activité"):
        st.subheader("🔍 Audit d'activité des utilisateurs DHIS2")
        data = get_user_logins(dhis2_url, headers)
        df = pd.DataFrame(data)

        # Correction ici : s'assurer que 'lastLogin' existe
        if 'lastLogin' not in df.columns:
            df['lastLogin'] = pd.NaT

        df['lastLogin'] = pd.to_datetime(df['lastLogin'], errors='coerce')

        df['Actif durant la période'] = df['lastLogin'].apply(
            lambda x: "Oui" if pd.notnull(x) and start_date <= x.date() <= end_date else "Non"
        )

        st.dataframe(df.sort_values("lastLogin", ascending=False), use_container_width=True)

        filtered = df[df["Actif durant la période"] == "Oui"]
        if not filtered.empty:
            excel_data = filtered.to_excel(index=False, engine='openpyxl')
            st.download_button(
                "📄 Exporter les actifs (Excel)",
                data=excel_data,
                file_name="utilisateurs_actifs.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Aucun utilisateur actif trouvé durant la période.")
else:
    st.warning("Veuillez renseigner vos identifiants DHIS2 pour commencer.")
