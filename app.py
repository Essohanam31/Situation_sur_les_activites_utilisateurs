# NOTE: Ce script nécessite que le module 'streamlit' soit installé dans votre environnement Python.
# Installez-le avec : pip install streamlit

import streamlit as st
import pandas as pd
import requests
import base64
from datetime import datetime, timedelta
from collections import defaultdict

st.set_page_config(page_title="DHIS2 - Utilisateurs par unité", layout="wide")

# URL DHIS2 fixe
dhis2_url = "https://togo.dhis2.org/dhis"

# Connexion utilisateur
st.sidebar.header("🔐 Connexion à DHIS2")
username = st.sidebar.text_input("Nom d'utilisateur", type="default")
password = st.sidebar.text_input("Mot de passe", type="password")

@st.cache_data(show_spinner=False)
def get_auth_header(username, password):
    token = f"{username}:{password}"
    encoded = base64.b64encode(token.encode()).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}

@st.cache_data(show_spinner=False)
def get_org_units(base_url, headers):
    url = f"{base_url}/api/organisationUnits.json"
    params = {"paging": "false", "fields": "id,name,level,parent[id]"}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("organisationUnits", [])

@st.cache_data(show_spinner=False)
def get_all_users(base_url, headers):
    url = f"{base_url}/api/users.json"
    params = {"paging": "false", "fields": "id,username,name,organisationUnits[id]"}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("users", [])

@st.cache_data(show_spinner=False)
def get_user_logins(base_url, headers):
    url = f"{base_url}/api/userCredentials?fields=username,lastLogin&paging=false"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get("userCredentials", [])
    else:
        return []

def build_org_tree(units):
    id_to_unit = {u['id']: u for u in units}
    children = defaultdict(list)
    for unit in units:
        parent_id = unit.get('parent', {}).get('id')
        if parent_id:
            children[parent_id].append(unit['id'])
    return id_to_unit, children

def assign_users_to_units(users):
    unit_to_users = defaultdict(list)
    for user in users:
        for ou in user.get('organisationUnits', []):
            unit_to_users[ou['id']].append(user)
    return unit_to_users

def aggregate_users(unit_id, children_map, unit_to_users, aggregated):
    users = unit_to_users.get(unit_id, []).copy()
    for child_id in children_map.get(unit_id, []):
        users.extend(aggregate_users(child_id, children_map, unit_to_users, aggregated))
    aggregated[unit_id] = users
    return users

if username and password:
    headers = get_auth_header(username, password)
    st.success("Connexion réussie à DHIS2")

    units = get_org_units(dhis2_url, headers)
    users = get_all_users(dhis2_url, headers)
    user_logins = get_user_logins(dhis2_url, headers)

    login_map = {u['username']: u.get('lastLogin') for u in user_logins}

    id_to_unit, children_map = build_org_tree(units)
    unit_to_users = assign_users_to_units(users)

    aggregated_users = {}
    root_ids = [u['id'] for u in units if u.get('level') == 1]
    for root_id in root_ids:
        aggregate_users(root_id, children_map, unit_to_users, aggregated_users)

    export_rows = []
    for unit_id, users in aggregated_users.items():
        unit = id_to_unit[unit_id]
        for user in users:
            export_rows.append({
                "Unité d'organisation": unit['name'],
                "Niveau": unit['level'],
                "Nom utilisateur": user['name'],
                "Nom de connexion": user['username'],
                "Dernière connexion": login_map.get(user['username'])
            })

    df_export = pd.DataFrame(export_rows)
    df_export['Dernière connexion'] = pd.to_datetime(df_export['Dernière connexion'], errors='coerce')

    st.subheader("📄 Liste des utilisateurs par unité d'organisation (niveau 5 à 1)")
    st.dataframe(df_export, use_container_width=True)

    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📁 Télécharger les utilisateurs (CSV)",
        data=csv,
        file_name="utilisateurs_dhis2_par_unite.csv",
        mime='text/csv'
    )

    # Résumé des effectifs
    st.subheader("📊 Résumé par niveau d'organisation")
    resume = df_export.groupby('Niveau')["Nom utilisateur"].count().reset_index()
    resume.columns = ["Niveau", "Nombre d'utilisateurs"]
    st.dataframe(resume)

else:
    st.warning("Veuillez vous connecter à DHIS2 pour commencer.")
