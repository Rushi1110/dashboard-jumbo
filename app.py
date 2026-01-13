import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- SETTINGS ---
st.set_page_config(page_title="Jumbo Homes Internal Dashboard", layout="wide")

@st.cache_data
def load_data():
    # Load all files using simplified names
    owners = pd.read_csv('Owners.csv')
    visits = pd.read_csv('Visits.csv')
    buyers = pd.read_csv('Buyers.csv')
    inspections = pd.read_csv('home_inspection.csv')
    homes = pd.read_csv('Homes.csv')
    catalogue = pd.read_csv('home_catalogue.csv')
    price_hist = pd.read_csv('price-history-new.csv')
    offers = pd.read_csv('offers.csv')
    admins = pd.read_csv('Admins.csv')
    
    # Pre-processing Floor Plans
    catalogue['has_fp'] = catalogue['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)
    
    # Clean Agent Names & Roles
    admins['First Name'] = admins['First Name'].str.strip()
    valid_roles = ['Buyer Agent', 'BSA', 'Buyer Success Agent']
    agent_list = admins[admins['Role'].isin(valid_roles)]['First Name'].unique().tolist()
    
    return owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins, agent_list

owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins, agent_list = load_data()

# --- SIDEBAR FILTERS (From Data Table) ---
st.sidebar.title("🔍 Filters")

# 1. Year Filter
years = sorted(list(visits['Internal/Year'].dropna().unique()), reverse=True)
selected_year = st.sidebar.selectbox("Year", [None] + years, index=1 if years else 0)

# 2. Month Filter
months = visits[visits['Internal/Year'] == selected_year]['Internal/Month'].dropna().unique().tolist()
selected_month = st.sidebar.selectbox("Month", [None] + months)

# 3. Week Filter
weeks = visits[(visits['Internal/Year'] == selected_year) & (visits['Internal/Month'] == selected_month)]['Internal/Week'].dropna().unique().tolist()
selected_week = st.sidebar.selectbox("Week", [None] + weeks)

# 4. Locality Filter (Unified)
all_localities = sorted(list(set(owners['Locality'].dropna().unique()) | set(visits['Visit_location'].dropna().unique())))
selected_locality = st.sidebar.multiselect("Locality", all_localities)

# 5. Agent Filter (Buyer Agents/BSA Only)
selected_agents = st.sidebar.multiselect("Agents", agent_list)

# --- FILTERING LOGIC ---
def apply_filters(df, year_col, month_col, week_col, loc_col=None):
    temp_df = df.copy()
    if selected_year: temp_df = temp_df[temp_df[year_col] == selected_year]
    if selected_month: temp_df = temp_df[temp_df[month_col] == selected_month]
    if selected_week: temp_df = temp_df[temp_df[week_col] == selected_week]
    if selected_locality and loc_col: temp_df = temp_df[temp_df[loc_col].isin(selected_locality)]
    return temp_df

f_owners = apply_filters(owners, 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Locality')
f_visits = apply_filters(visits, 'Internal/Year', 'Internal/Month', 'Internal/Week', 'Visit_location')
f_buyers = apply_filters(buyers, 'Dates/Current-Year', 'Dates/Created_month', 'Dates/Created_week', 'Location/Locality')

# Agent Filtering (Leaderboard specific)
if selected_agents:
    f_visits = f_visits[f_visits['WA_Msg/VA_Name'].isin(selected_agents) | f_visits['Internal/LeadOwner'].isin(selected_agents)]

# --- TABBED VIEW ---
tab1, tab2, tab3, tab4 = st.tabs(["🏆 Leaderboard", "📦 Supply", "🏠 SKU", "👤 Demand"])

# --- TAB 1: LEADERBOARD & POINTS ---
with tab1:
    st.header("Agent Performance Leaderboard")
    
    # Points Calculation
    agent_metrics = []
    v_comp = f_visits[f_visits['Status/Visit Completed'] == True]
    
    for agent in (selected_agents if selected_agents else agent_list):
        # Demand Points (Lead Owners)
        lo_v = v_comp[v_comp['Internal/LeadOwner'].str.contains(agent, na=False, case=False)]
        lo_pts = 0
        for phone, group in lo_v.groupby('Lead Phone'):
            # Check if repeat visitor (ever visited on another day)
            is_rv = visits[(visits['Lead Phone'] == phone) & (visits['Internal/Month'] != selected_month)].shape[0] > 0
            lo_pts += 7 if is_rv else 3
            
        # Managed Points (VAs)
        va_v = v_comp[v_comp['WA_Msg/VA_Name'] == agent]
        va_pts = len(va_v) * 4
        
        # Inspection Points
        insp_pts = len(inspections[inspections['Inspected By'].str.contains(agent, na=False, case=False)]) * 4
        
        agent_metrics.append({
            "Agent": agent,
            "Total Points": lo_pts + va_pts + insp_pts,
            "Visitors Scheduled": len(f_visits[f_visits['Internal/LeadOwner'].str.contains(agent, na=False)]),
            "Visitors Completed": len(lo_v),
            "Visits Managed": len(va_v),
            "Inspections": len(inspections[inspections['Inspected By'].str.contains(agent, na=False)])
        })

    leader_df = pd.DataFrame(agent_metrics).sort_values("Total Points", ascending=False)
    st.table(leader_df)

# --- TAB 2: SUPPLY ---
with tab2:
    st.header("Supply Funnel")
    col1, col2, col3 = st.columns(3)
    col1.metric("Owner Leads", len(f_owners))
    col2.metric("Owners Onboarded", len(f_owners[f_owners['Status'].isin(['Proposal Sent', 'Proposal Accepted'])]))
    
    regret_loss = pd.to_numeric(homes[homes['Internal/Status'] == 'On Hold']['Home/Ask_Price (lacs)'], errors='coerce').sum()
    col3.metric("Regrettable Loss", f"₹{regret_loss}L")

# --- TAB 3: SKU ---
with tab3:
    st.header("Inventory Analysis")
    st.metric("Live Homes", len(homes[homes['Internal/Status'] == 'Live']))
    st.write("Top Projects")
    top_projects = f_visits.groupby('Project').size().sort_values(ascending=False).head(10)
    st.bar_chart(top_projects)

# --- TAB 4: DEMAND ---
with tab4:
    st.header("Demand Funnel")
    b_leads = len(f_buyers)
    v_sched = f_visits['Lead Phone'].nunique()
    v_comp = f_visits[f_visits['Status/Visit Completed'] == True]['Lead Phone'].nunique()
    
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [b_leads, v_sched, v_comp],
        textinfo = "value+percent initial"
    ))
    st.plotly_chart(fig)
