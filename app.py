import streamlit as st
import pandas as pd
import sqlite3
import datetime
from fpdf import FPDF
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Mirvanie - Estimateur Immobilier", page_icon="🏠", layout="wide")

# --- INITIALISATION DE LA BASE DE DONNÉES SQLITE (pour l'admin) ---
def init_db():
    conn = sqlite3.connect('mirvanie_estimations.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS estimations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT, adresse TEXT, type_bien TEXT,
                  surface_habitable REAL, surface_terrain REAL,
                  estimation_totale REAL, details TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- CHARGEMENT DE LA GRILLE DE PRIX ---
@st.cache_data
def load_zones():
    try:
        df = pd.read_excel('mirvanie_grille_corrigee.xlsx', sheet_name='Zones')
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Erreur de chargement : {e}")
        return pd.DataFrame()

df_zones = load_zones()

# --- GÉNÉRATION DU RAPPORT PDF ---
def generate_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Rapport d'Estimation Mirvanie", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=12)
    for key, value in data.items():
        pdf.cell(0, 10, f"{key} : {value}", ln=True)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, "Ceci est une estimation indicative generee par l'algorithme Mirvanie.", ln=True)
    pdf.cell(0, 10, "Elle ne remplace pas une expertise immobiliere officielle.", ln=True)
    
    return pdf.output(dest='S').encode('latin-1')

# --- LOGIQUE D'ESTIMATION ---
def calculer_estimation(loc, type_bien, segment, surf_hab, surf_terrain, etat, doc, equipements, parking):
    # 1. Récupération des prix de base
    resultat = df_zones[(df_zones['localisation'] == loc) & 
                        (df_zones['type_bien'] == type_bien) & 
                        (df_zones['segment'] == segment)]
    
    if resultat.empty:
        return None, None, "Données non disponibles pour cette combinaison."
    
    prix_bati_m2 = (resultat.iloc[0]['prix_min_m2'] + resultat.iloc[0]['prix_max_m2']) / 2
    # On estime le prix du terrain à environ 30% du prix du bâti (hypothèse à affiner)
    prix_terrain_m2 = prix_bati_m2 * 0.30 
    
    # 2. Coefficients
    coef_etat = {"excellent": 1.10, "bon": 1.00, "moyen": 0.85, "à rénover": 0.60}
    coef_doc = {"Titre foncier": 1.15, "Arrêté de concession définitive": 1.10, 
                "Lettre d'attribution": 0.90, "Non communiqué": 0.80}
    
    # 3. Valeur du bâti
    valeur_bati = surf_hab * prix_bati_m2 * coef_etat.get(etat.lower(), 1.0)
    
    # 4. Valeur du terrain
    surf_terrain_libre = max(0, surf_terrain - surf_hab)
    valeur_terrain = surf_terrain_libre * prix_terrain_m2 * coef_doc.get(doc, 1.0)
    
    # 5. Ajout des équipements et parking
    bonus_equip = 0
    if "Piscine" in equipements: bonus_equip += 0.08
    if "Ascenseur" in equipements: bonus_equip += 0.05
    if "Groupe électrogène" in equipements or "Panneau solaire" in equipements: bonus_equip += 0.04
    if "Balcon/Terrasse" in equipements: bonus_equip += 0.03
    bonus_equip = min(bonus_equip, 0.20) # Plafond à 20%
    
    bonus_parking = min(parking * 0.03, 0.09)
    
    estimation_finale = (valeur_bati * (1 + bonus_equip + bonus_parking)) + valeur_terrain
    
    details = {
        "Valeur du bâti": f"{valeur_bati:,.0f} FCFA",
        "Valeur du terrain": f"{valeur_terrain:,.0f} FCFA",
        "Bonus équipements": f"{bonus_equip*100:+.1f}%",
        "Bonus parking": f"{bonus_parking*100:+.1f}%"
    }
    
    return estimation_finale, details, None

# --- INTERFACE PRINCIPALE ---
tab1, tab2 = st.tabs(["🏠 Estimateur", "🔐 Admin"])

with tab1:
    st.title("🏠 Mirvanie - Estimateur Immobilier")
    st.write("Renseignez les caractéristiques du bien pour obtenir une estimation basée sur les micro-zones de Côte d'Ivoire.")

    if not df_zones.empty:
        with st.form("estimation_form"):
            # --- SECTION LOCALISATION AVEC GÉOCODAGE ---
            st.subheader("📍 Localisation")
            
            # Champ de recherche d'adresse libre
            adresse_recherche = st.text_input("Recherchez une adresse (ex: Cocody Riviera, Abidjan) :", "")
            
            # Géocodage avec Nominatim
            if adresse_recherche:
                geolocator = Nominatim(user_agent="mirvanie_app")
                try:
                    location = geolocator.geocode(f"{adresse_recherche}, Côte d'Ivoire")
                    if location:
                        st.success(f"📍 Adresse trouvée : {location.address}")
                        # Affichage d'une carte (optionnel)
                        # st.map(pd.DataFrame({'lat': [location.latitude], 'lon': [location.longitude]}))
                    else:
                        st.warning("Adresse non trouvée. Veuillez sélectionner manuellement ci-dessous.")
                except GeocoderTimedOut:
                    st.warning("Le service de géocodage est temporairement indisponible.")

            # Sélection manuelle de secours
            communes = sorted(df_zones['localisation'].unique())
            loc_choisie = st.selectbox("Ou sélectionnez une micro-zone dans la liste :", communes)
            
            types_dispo = sorted(df_zones[df_zones['localisation'] == loc_choisie]['type_bien'].unique())
            type_choisi = st.selectbox("Type de bien :", types_dispo)
            
            segments_dispo = sorted(df_zones[(df_zones['localisation'] == loc_choisie) & 
                                             (df_zones['type_bien'] == type_choisi)]['segment'].unique())
            segment_choisi = st.selectbox("Marché (Neuf ou Ancien) :", segments_dispo)

            # --- SECTION CARACTÉRISTIQUES ---
            st.subheader("📐 Caractéristiques & Configuration")
            col1, col2 = st.columns(2)
            
            with col1:
                surface_habitable = st.number_input("Surface habitable (m²) :", min_value=10, max_value=10000, value=100, step=10)
                surface_terrain = st.number_input("Surface totale du terrain (m²) :", min_value=10, max_value=10000, value=100, step=10)
                etage = st.number_input("Étage (0 si villa/maison) :", min_value=0, max_value=50, value=0)
                nb_pieces = st.number_input("Nombre de pièces :", min_value=0, max_value=50, value=3)
                nb_chambres = st.number_input("Nombre de chambres :", min_value=0, max_value=20, value=2)
                nb_sdb = st.number_input("Nombre de salles de bain :", min_value=0, max_value=10, value=1)

            with col2:
                annee_construction = st.number_input("Année de construction :", min_value=1900, max_value=2026, value=2015)
                etat_bien = st.selectbox("État du bien :", ["excellent", "bon", "moyen", "à rénover"])
                
                doc_foncier = st.selectbox("Document foncier :", [
                    "Titre foncier", "Arrêté de concession définitive", "Certificat de mutation de propriété foncière",
                    "Certificat foncier rural", "Arrêté de concession provisoire", "Lettre d'attribution",
                    "Lettre d'attribution avec promesse de bail emphytéotique", "Arrêté de concession provisoire avec promesse de bail emphytéotique",
                    "Attestation de droit d'usage coutumier", "Attestation villageoise", "Bail emphytéotique",
                    "Acte notarié de vente", "Acte de vente sous seing privé", "Attestation coutumière",
                    "Autre document", "Non communiqué"
                ])
                
                parking_type = st.selectbox("Stationnement :", ["Aucun", "Rue", "Privé", "Garage"])
                nb_parking = st.number_input("Nombre de places (si privé/garage) :", min_value=0, max_value=10, value=1) if parking_type != "Aucun" else 0
                
                equipements = st.multiselect("Équipements supplémentaires :", [
                    "Balcon/Terrasse", "Ascenseur", "Piscine", "Chauffage", "eau chaude", 
                    "panneau solaire", "Groupe electogene"
                ])

            submit = st.form_submit_button("💰 Calculer l'estimation", use_container_width=True)

        # --- EXÉCUTION DU CALCUL ---
        if submit:
            estimation, details, erreur = calculer_estimation(
                loc_choisie, type_choisi, segment_choisi, 
                surface_habitable, surface_terrain, 
                etat_bien, doc_foncier, equipements, nb_parking
            )
            
            if erreur:
                st.warning(erreur)
            else:
                st.success("### 📊 Résultat de l'estimation Mirvanie")
                
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(label="Estimation Finale", value=f"{estimation:,.0f} FCFA")
                    st.info(f"📉 **Fourchette basse (-10%)** : {estimation * 0.90:,.0f} FCFA\n\n📈 **Fourchette haute (+10%)** : {estimation * 1.10:,.0f} FCFA")
                
                with col_res2:
                    st.write("**Détail du calcul :**")
                    for k, v in details.items():
                        st.write(f"- {k} : **{v}**")
                
                # --- ENREGISTREMENT EN BASE ---
                conn = sqlite3.connect('mirvanie_estimations.db')
                c = conn.cursor()
                c.execute('''INSERT INTO estimations 
                             (date, adresse, type_bien, surface_habitable, surface_terrain, estimation_totale, details)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), loc_choisie, type_choisi, 
                           surface_habitable, surface_terrain, estimation, str(details)))
                conn.commit()
                conn.close()

                # --- BOUTON DE TÉLÉCHARGEMENT PDF ---
                pdf_data = {
                    "Adresse": loc_choisie,
                    "Type de bien": type_choisi,
                    "Marché": segment_choisi,
                    "Surface habitable": f"{surface_habitable} m²",
                    "Surface terrain": f"{surface_terrain} m²",
                    "État": etat_bien,
                    "Document foncier": doc_foncier,
                    "Estimation totale": f"{estimation:,.0f} FCFA"
                }
                pdf_bytes = generate_pdf(pdf_data)
                st.download_button(
                    label="📄 Télécharger le rapport d'estimation (PDF)",
                    data=pdf_bytes,
                    file_name="rapport_estimation_mirvanie.pdf",
                    mime="application/pdf"
                )
    else:
        st.error("Impossible de charger la base de données.")

# --- ONGLET ADMIN ---
with tab2:
    st.title("🔐 Tableau de Bord Administrateur")
    
    # Authentification simple
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Mot de passe administrateur :", type="password")
        if st.button("Se connecter"):
            # Remplacez "admin123" par un mot de passe plus sécurisé
            if password == "admin123":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
    else:
        st.success("Connecté en tant qu'administrateur.")
        if st.button("Se déconnecter"):
            st.session_state.authenticated = False
            st.rerun()
        
        # Affichage des estimations
        conn = sqlite3.connect('mirvanie_estimations.db')
        df_estimations = pd.read_sql_query("SELECT * FROM estimations ORDER BY id DESC", conn)
        conn.close()
        
        if not df_estimations.empty:
            st.metric("Nombre total d'estimations", len(df_estimations))
            st.dataframe(df_estimations)
            
            # Graphique simple
            st.bar_chart(df_estimations['type_bien'].value_counts())
        else:
            st.info("Aucune estimation enregistrée pour le moment.")