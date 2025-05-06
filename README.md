
# DHIS2 - Détection des doublons & Audit d'activité

Cette application **Streamlit** permet de :
- Identifier les doublons d’utilisateurs dans DHIS2 basés sur le **nom complet**.
- Lister les utilisateurs par **unité d'organisation**.
- Auditer les **connexions** des utilisateurs sur une période donnée.

---

## ✅ Fonctionnalités

### 🔐 Connexion
- Authentification via l’URL DHIS2, le nom d’utilisateur et le mot de passe.
- Requêtes API sécurisées avec entête d'autorisation `Basic`.

### 🏥 Unité d'organisation
- Sélection d’une unité d’organisation via un menu déroulant.
- Chargement des utilisateurs associés à cette unité.

### 🧍‍♂️ Détection des doublons
- Utilisateurs marqués comme **doublon** si le nom complet est dupliqué.
- Export en CSV.

### 📊 Audit de connexion
- Sélection d’une **période de dates**.
- Visualisation des utilisateurs connectés durant la période.
- Export en Excel des utilisateurs actifs.

---

## 🚀 Lancer l'application

### 1. Cloner ou télécharger le dossier

```bash
cd dhis2_users_audit_app
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Démarrer l'application

```bash
streamlit run app.py
```

---

## 🧩 Technologies

- Python
- Streamlit
- Pandas
- Requests

---

## 🔒 Remarque

Les identifiants DHIS2 ne sont **pas stockés**. Ils sont uniquement utilisés en session pour interroger l’API DHIS2.

---

## 📄 Auteur

Développé avec ❤️ pour aider à la gouvernance des utilisateurs DHIS2.
