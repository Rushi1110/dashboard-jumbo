import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. SETTINGS ---
st.set_page_config(page_title="Jumbo Homes | Internal Tool", layout="wide")

# --- 2. DATA LOADING (Pulling categorical dates from tables) ---
@st.cache_data
def load_and_standardize():
    f_map = {
        'owners': 'Owners.csv', 'visits': 'Visits.csv', 'buyers': 'Buyers.csv',
        'inspections': 'home_inspection.csv', 'homes': 'Homes.csv',
        'catalogue': 'home_catalogue.csv', 'price_hist': 'price-history-new.csv',
        'offers': 'offers.csv', 'admins': 'Admins.csv'
    }
    
    data = {k: pd.read_csv(v) for k, v in f_map.items()}

    # Standardize Column Naming for Filtering
    # Visits
    data['visits']['Project'] = data['visits']['Homes_Visited'].astype(str).apply(lambda x: x.split('_')[0] if '_' in x else "Unknown")
    data['visits']['is_comp'] = (data['visits']['Status/Visit Completed'] == True)
    
    # Catalogue Floor Plan Check
    data['catalogue']['has_fp'] = data['catalogue']['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)

    # Admin Role Mapping
    data['admins']['Role'] = data['admins']['Role'].fillna('Unknown').str.strip()
    
    return data

data = load_and_standardize()

# --- 3. DYNAMIC SIDEBAR FILTERS ---
st.sidebar.title("🔍 Deep-Dive Filters")

# Date Filters derived from categorical columns in Visits.csv
avail_years = sorted(data['visits']['Internal/Year'].dropna().unique().tolist(), reverse=True)
sel_year = st.sidebar.selectbox("Filter by Year", [None] + avail_years, index=1 if len(avail_years) > 0 else 0)

avail_months = sorted(data['visits'][data['visits']['Internal/Year'] == sel_year]['Internal/Month'].dropna().unique().tolist()) if sel_year else []
sel_month = st.sidebar.selectbox("Filter by Month", [None] + avail_months)

avail_weeks = sorted(data['visits'][(data['visits']['Internal/Year'] == sel_year) & (data['visits']['Internal/Month'] == sel_month)]['Internal/Week'].dropna().unique().tolist()) if sel_month else []
sel_week = st.sidebar.selectbox("Filter by Week", [None] + avail_weeks)

# Locality Filter (Consolidated)
localities = sorted(list(set(data['owners']['Locality'].dropna()) | set(data['visits']['Visit_location'].dropna())))
sel_loc = st.sidebar.multiselect("Locality Analysis", localities)

# Agent Filter (Restricted to Buyer Agent & BSA)
target_roles = ['Buyer Agent', 'BSA', 'Buyer Success Agent']
agent_df = data['admins'][data['admins']['Role'].isin(target_roles)]
agent_list = sorted(agent_df['First Name'].dropna().unique().tolist())
sel_agents = st.sidebar.multiselect("Agent Analysis", agent_list)

# --- 4. DATA FILTERING ENGINE ---
def filter_df(df, y_col, m_col, w_col, l_col=None):
    df_f = df.copy()
    if sel_year: df_f = df_f[df_f[y_col] == sel_year]
    if sel_month: df_f = df_f[df_f[m_col] == sel_month]
    if sel_week: df_f = df_f[df_f[w_col] == sel_week]
    if sel_loc and l_col: df_f = df_f[df_f[l_col].isin(sel_loc)]
    return df_f

v_f = filter_df(data['visits'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Visit_location')
o_f = filter_df(data['owners'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Locality')
b_f = filter_df(data['buyers'], 'Dates/Current-Year', 'Dates/Created_month', 'Dates/Created_week', 'Location/Locality')
h_f = filter_df(data['homes'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Building/Locality')

# --- 5. VISUALIZATION TABS ---
tab_lead, tab_supply, tab_sku, tab_demand, tab_admin = st.tabs([
    "🏆 Leaderboard", "📦 Supply", "🏠 SKU Analysis", "👤 Demand", "⚙️ Admin Overrides"
])

with tab_admin:
    st.subheader("Point Multipliers")
    col1, col2 = st.columns(2)
    tour_pts_val = col1.number_input("Pts per Tour", value=20)
    rate_pts_val = col2.number_input("Pts per Google Rating", value=10)
    
    manual_data = {}
    for person in (sel_agents if sel_agents else agent_list):
        c1, c2 = st.columns(2)
        t = c1.number_input(f"Tours: {person}", 0, key=f"t_{person}")
        r = c2.number_input(f"Ratings: {person}", 0, key=f"r_{person}")
        manual_data[person] = (t * tour_pts_val) + (r * rate_pts_val)

with tab_lead:
    st.header("Buyer Agent & BSA Performance")
    
    
    leaderboard = []
    # Use selected agents if any, else all Buyer/BSA
    for name in (sel_agents if sel_agents else agent_list):
        # Point Logic (Lead Owner side)
        agent_v = v_f[(v_f['Internal/LeadOwner'].str.contains(name, na=False, case=False)) & (v_f['is_comp'] == True)]
        lo_pts = 0
        for phone, group in agent_v.groupby('Lead Phone'):
            # RV = Visited in a different month previously
            is_rv = data['visits'][(data['visits']['Lead Phone'] == phone) & (data['visits']['Internal/Month'] != sel_month)].shape[0] > 0
            lo_pts += 7 if is_rv else 3
            
        # Point Logic (VA side)
        va_v = v_f[(v_f['WA_Msg/VA_Name'] == name) & (v_f['is_comp'] == True)]
        va_pts = len(va_v) * 4
        
        # Point Logic (Inspection side)
        insp = data['inspections'][data['inspections']['Inspected By'].str.contains(name, na=False, case=False)]
        insp_pts = len(insp) * 4
        
        leaderboard.append({
            "Agent": name,
            "Total Score": lo_pts + va_pts + insp_pts + manual_data.get(name, 0),
            "Scheduled": v_f[v_f['Internal/LeadOwner'].str.contains(name, na=False)]['Lead Phone'].nunique(),
            "Completed": agent_v['Lead Phone'].nunique(),
            "Managed (VA)": len(va_v),
            "Inspections": len(insp)
        })
    
    st.table(pd.DataFrame(leaderboard).sort_values("Total Score", ascending=False))

with tab_supply:
    st.header("Supply Health")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Owner Leads", len(o_f))
    onboarded_owners = len(o_f[o_f['Status'].isin(['Proposal Sent', 'Proposal Accepted'])])
    m2.metric("Owners Onboarded", onboarded_owners)
    regret = pd.to_numeric(h_f[h_f['Internal/Status'] == 'On Hold']['Home/Ask_Price (lacs)'], errors='coerce').sum()
    m3.metric("Regrettable Loss", f"₹{regret}L")

with tab_sku:
    st.header("Project Performance")
    st.metric("Live Inventory", len(h_f[h_f['Internal/Status'] == 'Live']))
    st.write("### Top Projects by Visits")
    if not v_f.empty:
        proj_counts = v_f['Project'].value_counts().head(10)
        st.bar_chart(proj_counts)

with tab_demand:
    st.header("Demand Metrics")
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [len(b_f), v_f['Lead Phone'].nunique(), v_f[v_f['is_comp'] == True]['Lead Phone'].nunique()],
        textinfo = "value+percent initial"
    ))
    st.plotly_chart(fig, use_container_width=True)
