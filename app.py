import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="Jumbo Homes | Internal Tool", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; }
    .main { background-color: #f8f9fb; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ROBUST DATA LOADING ---
@st.cache_data
def load_and_clean_data():
    # Load files with simplified names
    f_map = {
        'owners': 'Owners.csv', 'visits': 'Visits.csv', 'buyers': 'Buyers.csv',
        'inspections': 'home_inspection.csv', 'homes': 'Homes.csv',
        'catalogue': 'home_catalogue.csv', 'price_hist': 'price-history-new.csv',
        'offers': 'offers.csv', 'admins': 'Admins.csv'
    }
    
    data = {}
    for key, path in f_map.items():
        try:
            data[key] = pd.read_csv(path)
        except Exception:
            st.error(f"Critical Error: Missing file {path}")
            st.stop()

    # Derived Column: Project Name (Extracted from HID)
    data['visits']['Project'] = data['visits']['Homes_Visited'].astype(str).apply(lambda x: x.split('_')[0] if '_' in x else "Unknown")
    
    # Floor Plan Verification (Non-null + https)
    data['catalogue']['has_fp'] = data['catalogue']['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)

    # Standardize Visit Completion
    data['visits']['is_comp'] = (data['visits']['Status/Visit Completed'] == True) | (data['visits']['Status/Visit_status'].str.contains('Completed', na=False))

    # Clean Admin Roles
    data['admins']['Role'] = data['admins']['Role'].fillna('Unknown').str.strip()
    
    return data

data = load_and_clean_data()

# --- 3. DYNAMIC SIDEBAR FILTERS (From Datatables) ---
st.sidebar.title("📊 Filter Engine")

# Date Filters (from Visits table)
years = sorted([y for y in data['visits']['Internal/Year'].dropna().unique()], reverse=True)
sel_year = st.sidebar.selectbox("Year", [None] + years, index=1 if len(years) > 0 else 0)

months = sorted(data['visits'][data['visits']['Internal/Year'] == sel_year]['Internal/Month'].dropna().unique().tolist()) if sel_year else []
sel_month = st.sidebar.selectbox("Month", [None] + months)

weeks = sorted(data['visits'][(data['visits']['Internal/Year'] == sel_year) & (data['visits']['Internal/Month'] == sel_month)]['Internal/Week'].dropna().unique().tolist()) if sel_month else []
sel_week = st.sidebar.selectbox("Week", [None] + weeks)

# Locality Filter (Consolidated from all tables)
localities = sorted(list(set(data['owners']['Locality'].dropna()) | set(data['visits']['Visit_location'].dropna())))
sel_loc = st.sidebar.multiselect("Locality / Zone", localities)

# Agent Filter (Buyer Agents and BSA Only)
target_roles = ['Buyer Agent', 'BSA', 'Buyer Success Agent']
agent_df = data['admins'][data['admins']['Role'].isin(target_roles)]
agent_list = sorted(agent_df['First Name'].dropna().unique().tolist())
sel_agents = st.sidebar.multiselect("Agents (Lead Owners/VAs)", agent_list)

# --- 4. FILTERING ENGINE ---
def apply_global_filters(df, y_col, m_col, w_col, l_col=None, agent_col=None):
    df_f = df.copy()
    if sel_year: df_f = df_f[df_f[y_col] == sel_year]
    if sel_month: df_f = df_f[df_f[m_col] == sel_month]
    if sel_week: df_f = df_f[df_f[w_col] == sel_week]
    if sel_loc and l_col: df_f = df_f[df_f[l_col].isin(sel_loc)]
    return df_f

v_f = apply_global_filters(data['visits'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Visit_location')
o_f = apply_global_filters(data['owners'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Locality')
b_f = apply_global_filters(data['buyers'], 'Dates/Current-Year', 'Dates/Created_month', 'Dates/Created_week', 'Location/Locality')
h_f = apply_global_filters(data['homes'], 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Building/Locality')

# --- 5. TABS & VISUALS ---
tab_lead, tab_supply, tab_sku, tab_demand = st.tabs(["🏆 Leaderboard", "📦 Supply", "🏠 SKU Analysis", "👤 Demand"])

with tab_lead:
    st.subheader("Agent Performance Points")
    
    
    leaderboard = []
    # Points logic implementation
    for name in (sel_agents if sel_agents else agent_list):
        # 1. Lead Owner Points (3 for new, 7 for RV)
        agent_v = v_f[(v_f['Internal/LeadOwner'].str.contains(name, na=False, case=False)) & (v_f['is_comp'] == True)]
        pts_lo = 0
        for phone, group in agent_v.groupby('Lead Phone'):
            is_rv = data['visits'][(data['visits']['Lead Phone'] == phone) & (data['visits']['Internal/Month'] != sel_month)].shape[0] > 0
            pts_lo += 7 if is_rv else 3
            
        # 2. VA Points (4 per Managed Visit)
        va_v = v_f[(v_f['WA_Msg/VA_Name'] == name) & (v_f['is_comp'] == True)]
        pts_va = len(va_v) * 4
        
        # 3. Inspection Points (4 per Inspection)
        insp = data['inspections'][data['inspections']['Inspected By'].str.contains(name, na=False, case=False)]
        pts_ins = len(insp) * 4
        
        leaderboard.append({
            "Agent": name,
            "Total Points": pts_lo + pts_va + pts_ins,
            "Visitors Scheduled": v_f[v_f['Internal/LeadOwner'].str.contains(name, na=False)]['Lead Phone'].nunique(),
            "Visitors Completed": agent_v['Lead Phone'].nunique(),
            "Visits Managed": len(va_v),
            "Inspections Done": len(insp)
        })
    
    st.table(pd.DataFrame(leaderboard).sort_values("Total Points", ascending=False))

with tab_supply:
    st.header("Supply Funnel")
    c1, c2, c3 = st.columns(3)
    c1.metric("Owner Leads", len(o_f))
    c2.metric("Owners Onboarded", len(o_f[o_f['Status'].isin(['Proposal Sent', 'Proposal Accepted'])]))
    
    regret = pd.to_numeric(h_f[h_f['Internal/Status'] == 'On Hold']['Home/Ask_Price (lacs)'], errors='coerce').sum()
    c3.metric("Regrettable Loss", f"₹{regret}L")

with tab_sku:
    st.header("Inventory (SKU) Stats")
    live = h_f[h_f['Internal/Status'] == 'Live']
    st.metric("Live Homes", len(live))
    
    st.subheader("Top Projects by Activity")
    if not v_f.empty:
        # Fixed KeyError: Ensure column exists before grouping
        proj_counts = v_f['Project'].value_counts().head(10)
        st.bar_chart(proj_counts)

with tab_demand:
    st.header("Demand Conversion")
    v_sched = v_f['Lead Phone'].nunique()
    v_comp = v_f[v_f['is_comp'] == True]['Lead Phone'].nunique()
    
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [len(b_f), v_sched, v_comp],
        textinfo = "value+percent initial"
    ))
    st.plotly_chart(fig, use_container_width=True)
