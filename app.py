import streamlit as st
import pandas as pd
import requests
import base64
from collections import defaultdict
from datetime import datetime, timedelta

st.set_page_config(page_title="Audit DHIS2 - Utilisateurs par Unité", layout="wide")

# URL DHIS2
dhis2_url = "https://togo.dhis2.org/dhis"

# Connexion
st.sidebar.header("🔐 Connexion à DHIS2")
username = st.sidebar.text_input("Nom d'utilisateur")
password = st.sidebar.text_input("Mot de passe", type="password")

@st.cache_data(show_spinner=False)
def get_auth_header(username, password):
    token = f"{username}:{password}"
    encoded = base64.b64encode(token.encode()).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}

@st.cache_data(show_spinner=True)
def get_org_units(url, headers):
    all_units = []
    next_page = f"{url}/api/organisationUnits?paging=false&fields=id,name,level,parent[id],path"
    r = requests.get(next_page, headers=headers)
    r.raise_for_status()
    all_units.extend(r.json().get("organisationUnits", []))
    return all_units

@st.cache_data(show_spinner=True)
def get_users(url, headers):
    r = requests.get(f"{url}/api/users.json?paging=false&fields=id,username,name,organisationUnits[id]", headers=headers)
    r.raise_for_status()
    return r.json().get("users", [])

@st.cache_data(show_spinner=True)
def get_user_logins(url, headers):
    r = requests.get(f"{url}/api/userCredentials?fields=username,lastLogin&paging=false", headers=headers)
    if r.status_code == 200:
        return r.json().get("userCredentials", [])
    return []

if username and password:
    headers = get_auth_header(username, password)

    with st.spinner("Chargement des unités d'organisation..."):
        org_units = get_org_units(dhis2_url, headers)
        org_df = pd.DataFrame(org_units)

    id_to_name = {row['id']: row['name'] for row in org_units}
    id_to_level = {row['id']: row['level'] for row in org_units}
    id_to_parent = {row['id']: row.get('parent', {}).get('id', None) for row in org_units}
    id_to_path = {row['id']: row.get('path', '') for row in org_units}

    unit_tree = defaultdict(list)
    for ou in org_units:
        parent_id = ou.get('parent', {}).get('id')
        if parent_id:
            unit_tree[parent_id].append(ou['id'])

    st.sidebar.markdown("### 🎯 Sélection du niveau")
    selected_level = st.sidebar.selectbox("Choisir un niveau à afficher :", [6, 5, 4, 3, 2, 1], index=1)

    st.sidebar.markdown("### 📤 Charger et afficher les utilisateurs")
    if st.sidebar.button("Charger les utilisateurs"):
        with st.spinner("Chargement des utilisateurs..."):
            users = get_users(dhis2_url, headers)

        org_users = defaultdict(list)
        for user in users:
            user_name = user.get('name', '')
            user_username = user.get('username', '')
            for org_unit in user.get('organisationUnits', []):
                org_unit_id = org_unit['id']
                if org_unit_id in id_to_name:
                    org_users[org_unit_id].append({
                        "Nom complet": user_name,
                        "Nom de connexion": user_username
                    })

        agg_users = defaultdict(list)
        for unit_id, user_list in org_users.items():
            path = id_to_path.get(unit_id, '')
            path_ids = path.strip('/').split('/')
            for level_id in path_ids:
                agg_users[level_id].extend(user_list)

        data = []
        for unit_id, user_list in agg_users.items():
            level = id_to_level.get(unit_id, None)
            if level and level <= 6 and level >= selected_level:
                for user in user_list:
                    data.append({
                        "Nom complet": user.get("Nom complet", ""),
                        "Nom de connexion": user.get("Nom de connexion", ""),
                        "Unité d'organisation": id_to_name.get(unit_id, ""),
                        "Niveau": level,
                        "ID unité": unit_id
                    })

        df_users = pd.DataFrame(data).drop_duplicates()

        st.success(f"{len(df_users)} utilisateurs trouvés à partir du niveau {selected_level}.")
        st.dataframe(df_users, use_container_width=True)

        csv = df_users.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Télécharger au format CSV",
            data=csv,
            file_name=f"utilisateurs_dhis2_niveau_{selected_level}.csv",
            mime='text/csv'
        )

    # Section Analyse activité
    st.sidebar.markdown("### 🕵️‍♂️ Audit de Connexions")
    start_date = st.sidebar.date_input("Date de début", datetime.today() - timedelta(days=30))
    end_date = st.sidebar.date_input("Date de fin", datetime.today())

    if start_date > end_date:
        st.sidebar.error("❌ Date de début > date de fin.")
    elif st.sidebar.button("Analyser les connexions"):
        st.subheader("📊 Connexions des utilisateurs")
        with st.spinner("Analyse des connexions..."):
            login_data = get_user_logins(dhis2_url, headers)
            df_logins = pd.DataFrame(login_data)
            df_logins['lastLogin'] = pd.to_datetime(df_logins.get('lastLogin'), errors='coerce')

            df_logins["Actif durant la période"] = df_logins['lastLogin'].apply(
                lambda x: "Oui" if pd.notnull(x) and start_date <= x.date() <= end_date else "Non"
            )

            st.dataframe(df_logins.sort_values("lastLogin", ascending=False), use_container_width=True)

            actifs = df_logins[df_logins["Actif durant la période"] == "Oui"]
            if not actifs.empty:
                excel_data = actifs.to_excel(index=False, engine='openpyxl')
                st.download_button(
                    label="📥 Télécharger les actifs (Excel)",
                    data=excel_data,
                    file_name="utilisateurs_actifs.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("Aucun utilisateur actif durant la période.")
else:
    st.warning("🔑 Veuillez renseigner vos identifiants DHIS2 pour commencer.")
