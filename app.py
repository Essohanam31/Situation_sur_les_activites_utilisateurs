# NOTE: Ce script nécessite que le module 'streamlit' soit installé dans votre environnement Python.
# Installez-le avec : pip install streamlit

import streamlit as st
import pandas as pd
import requests
import base64
from datetime import datetime, timedelta
from collections import defaultdict

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
    params = {"paging": "false", "fields": "id,name,parent[id]"}
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

# Construire la hiérarchie ascendante des unités
def build_ou_hierarchy(units):
    hierarchy = defaultdict(list)
    lookup = {unit['id']: unit for unit in units}
    for unit in units:
        current = unit
        while 'parent' in current and current['parent'] and current['parent']['id'] in lookup:
            parent_id = current['parent']['id']
            hierarchy[unit['id']].append(parent_id)
            current = lookup[parent_id]
    return hierarchy

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

        users_data = get_users(dhis2_url, headers)
        logins_data = get_user_logins(dhis2_url, headers)

        df_users = pd.DataFrame(users_data)[['id', 'username', 'name', 'organisationUnits']]
        df_logins = pd.DataFrame(logins_data)[['username', 'lastLogin']]

        df = pd.merge(df_users, df_logins, on='username', how='left')
        df['lastLogin'] = pd.to_datetime(df['lastLogin'], errors='coerce')

        df['Actif durant la période'] = df['lastLogin'].apply(
            lambda x: "Oui" if pd.notnull(x) and start_date <= x.date() <= end_date else "Non"
        )
        df['Jamais connecté'] = df['lastLogin'].isna().map({True: "Oui", False: "Non"})

        hierarchy = build_ou_hierarchy(units)

        region_totals = defaultdict(lambda: {'Total': 0, 'Actifs': 0, 'Jamais connectés': 0})
        for _, row in df.iterrows():
            assigned_ous = [ou['id'] for ou in row['organisationUnits']]
            ou_set = set(assigned_ous)
            for ou in assigned_ous:
                ou_set.update(hierarchy.get(ou, []))
            for ou_id in ou_set:
                region_totals[ou_id]['Total'] += 1
                if row['Actif durant la période'] == "Oui":
                    region_totals[ou_id]['Actifs'] += 1
                if row['Jamais connecté'] == "Oui":
                    region_totals[ou_id]['Jamais connectés'] += 1

        st.write(f"🔢 Nombre d'utilisateurs avec une date de connexion connue : {df['lastLogin'].notnull().sum()}")
        st.dataframe(df.sort_values("lastLogin", ascending=False), use_container_width=True)

        if region_totals:
            st.write("\n### 🧾 Résumé par unité d'organisation (hiérarchie cumulée)")
            summary_data = []
            for ou_id, metrics in region_totals.items():
                name = next((unit['name'] for unit in units if unit['id'] == ou_id), ou_id)
                summary_data.append({
                    "Unité d'organisation": name,
                    "Utilisateurs totaux": metrics['Total'],
                    "Actifs": metrics['Actifs'],
                    "Jamais connectés": metrics['Jamais connectés']
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.write("### 📤 Export utilisateurs actifs")
            actifs = df[df["Actif durant la période"] == "Oui"]
            if not actifs.empty:
                csv_actifs = actifs.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Télécharger les actifs", data=csv_actifs, file_name="utilisateurs_actifs.csv", mime="text/csv")
            else:
                st.info("Aucun utilisateur actif trouvé durant la période.")

        with col2:
            st.write("### 🚫 Export jamais connectés")
            jamais_connectes = df[df["Jamais connecté"] == "Oui"]
            if not jamais_connectes.empty:
                csv_jamais = jamais_connectes.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Télécharger les jamais connectés", data=csv_jamais, file_name="utilisateurs_jamais_connectes.csv", mime="text/csv")
            else:
                st.info("Tous les utilisateurs se sont déjà connectés au moins une fois.")
else:
    st.warning("Veuillez renseigner vos identifiants DHIS2 pour commencer.")
