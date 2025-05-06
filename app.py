import streamlit as st
import requests
import pandas as pd
from requests.auth import HTTPBasicAuth

st.set_page_config(page_title="Utilisateurs DHIS2 par unité d'organisation", layout="wide")

st.title("📊 Export des utilisateurs DHIS2 par unité d'organisation (du niveau 5 au niveau 1)")

# Connexion à DHIS2
with st.sidebar:
    st.header("🔐 Connexion DHIS2")
    dhis2_url = st.text_input("URL de DHIS2", value="https://play.dhis2.org/40.0.3", help="Ex: https://instance.dhis2.org")
    username = st.text_input("Nom d'utilisateur", value="admin", type="default")
    password = st.text_input("Mot de passe", value="district", type="password")

def get_auth_header(username, password):
    return {"Authorization": f"Basic {requests.auth._basic_auth_str(username, password).split(' ')[1]}"}

@st.cache_data(show_spinner=False)
def get_full_org_units(base_url, headers):
    url = f"{base_url}/api/organisationUnits.json"
    params = {
        "paging": "false",
        "fields": "id,name,level,parent[id]"
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("organisationUnits", [])

def build_hierarchy(units):
    children_map = {}
    id_map = {u["id"]: u for u in units}
    for u in units:
        parent_id = u.get("parent", {}).get("id")
        if parent_id:
            children_map.setdefault(parent_id, []).append(u["id"])
    return children_map, id_map

@st.cache_data(show_spinner=False)
def get_all_users(base_url, headers):
    url = f"{base_url}/api/users.json"
    params = {
        "paging": "false",
        "fields": "id,username,name,organisationUnits[id]"
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json().get("users", [])

def aggregate_users_by_unit(units, users, children_map):
    user_map = {u["id"]: {"username": u["username"], "name": u["name"], "organisationUnits": [ou["id"] for ou in u.get("organisationUnits", [])]} for u in users}
    users_per_unit = {u["id"]: [] for u in units}

    for user in users:
        for ou in user.get("organisationUnits", []):
            users_per_unit[ou["id"]].append(user)

    def gather_users(unit_id):
        all_users = list(users_per_unit.get(unit_id, []))
        for child_id in children_map.get(unit_id, []):
            all_users.extend(gather_users(child_id))
        return all_users

    return {unit["id"]: gather_users(unit["id"]) for unit in units}

if username and password and dhis2_url:
    headers = get_auth_header(username, password)

    st.header("👥 Utilisateurs par unité d'organisation (de la FOSA au niveau national)")

    with st.spinner("Chargement des données..."):
        try:
            units = get_full_org_units(dhis2_url, headers)
            children_map, id_map = build_hierarchy(units)
            users = get_all_users(dhis2_url, headers)
            aggregated = aggregate_users_by_unit(units, users, children_map)
        except Exception as e:
            st.error(f"Erreur lors de la récupération des données : {e}")
            st.stop()

    units_from_level5 = [u for u in units if u["level"] >= 5]

    for unit in sorted(units_from_level5, key=lambda x: (x["level"], x["name"])):
        users_for_unit = aggregated.get(unit["id"], [])
        if users_for_unit:
            st.subheader(f"📍 {unit['name']} (Niveau {unit['level']}) - {len(users_for_unit)} utilisateurs")
            df = pd.DataFrame(users_for_unit)[["username", "name"]]
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📄 Télécharger - {unit['name']}",
                data=csv,
                file_name=f"utilisateurs_{unit['name'].replace(' ', '_')}.csv",
                mime='text/csv'
            )
