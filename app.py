import streamlit as st
import pandas as pd
import requests
import base64
from datetime import datetime, timedelta

st.set_page_config(page_title="DHIS2 - Doublons & Audit", layout="wide")

# Onglet Connexion
st.sidebar.header("🔐 Connexion à DHIS2")
dhis2_url = st.sidebar.text_input("URL DHIS2", value="https://ton_instance.dhis2.org/dhis")
username = st.sidebar.text_input("Nom d'utilisateur", type="default")
password = st.sidebar.text_input("Mot de passe", type="password")

@st.cache_data(show_spinner=False)
def get_auth_header(username, password):
    token = f"{username}:{password}"
    encoded = base64.b64encode(token.encode()).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}

@st.cache_data(show_spinner=False)
def get_organisation_units(base_url, headers):
    url = f"{base_url}/api/organisationUnits.json"
    params = {"paging": "false", "fields": "id,name"}
    r = requests.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json().get("organisationUnits", [])
    return []

def get_users(base_url, headers, org_unit_id):
    url = f"{base_url}/api/users.json"
    params = {
        "paging": "false",
        "fields": "id,username,name,organisationUnits[id]"
    }
    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        st.error("Erreur lors de la récupération des utilisateurs.")
        return []
    users = r.json().get("users", [])
    filtered = []
    for user in users:
        user_ous = [ou['id'] for ou in user.get('organisationUnits', [])]
        if org_unit_id in user_ous:
            filtered.append(user)
    return filtered

@st.cache_data(show_spinner=False)
def get_user_logins(base_url, headers):
    url1 = f"{base_url}/api/userCredentials.json?fields=username,lastLogin&paging=false"
    r1 = requests.get(url1, headers=headers)
    if r1.status_code == 200:
        data = r1.json().get("userCredentials", [])
        if any("lastLogin" in user for user in data):
            return data
    else:
        st.warning(f"Erreur avec userCredentials: {r1.status_code} - {r1.text}")

    url2 = f"{base_url}/api/users.json?fields=username,lastLogin&paging=false"
    r2 = requests.get(url2, headers=headers)
    if r2.status_code == 200:
        data = r2.json().get("users", [])
        if any("lastLogin" in user for user in data):
            return data
        else:
            st.warning("Aucune information de connexion (lastLogin) trouvée dans les utilisateurs.")
            return []
    else:
        st.error(f"Erreur avec /users: {r2.status_code} - {r2.text}")
        return []

if username and password and dhis2_url:
    headers = get_auth_header(username, password)

    st.sidebar.subheader("🏥 Sélection de l'unité d'organisation")
    units = get_organisation_units(dhis2_url, headers)
    unit_options = {unit['name']: unit['id'] for unit in units}

    if unit_options:
        selected_name = st.sidebar.selectbox("Choisir une unité", list(unit_options.keys()))
        selected_id = unit_options[selected_name]

        if st.sidebar.button("📥 Charger les utilisateurs"):
            st.info(f"Chargement des utilisateurs pour l'unité : {selected_name}")
            users = get_users(dhis2_url, headers, selected_id)

            if users:
                df_users = pd.DataFrame(users)
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

        if df.empty or 'lastLogin' not in df.columns:
            st.warning("Aucune donnée d'audit disponible ou champ 'lastLogin' manquant.")
            st.stop()

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
    st.warning("Veuillez renseigner vos identifiants DHIS2 pour commencer.")
