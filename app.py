import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Jumbo Homes | Internal Tool", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATA LOADING & CACHING ---
def parse_dt(df, cols):
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True).dt.tz_localize(None)
    return df

@st.cache_data
def load_all_data():
    try:
        owners = parse_dt(pd.read_csv('Owners.csv'), ['Internal/Created On'])
        visits = parse_dt(pd.read_csv('Visits.csv'), ['Scheduled Date'])
        buyers = parse_dt(pd.read_csv('Buyers.csv'), ['Dates/Created On'])
        inspections = parse_dt(pd.read_csv('home_inspection.csv'), ['Inspected On'])
        homes = parse_dt(pd.read_csv('Homes.csv'), ['Internal/Created On', 'Offboarding/DateTime'])
        catalogue = pd.read_csv('home_catalogue.csv')
        price_hist = parse_dt(pd.read_csv('price-history-new.csv'), ['date'])
        offers = parse_dt(pd.read_csv('offers.csv'), ['Offer Date'])
        admins = pd.read_csv('Admins.csv')
        
        # Pre-processing
        visits['Project'] = visits['Homes_Visited'].str.split('_').str[0]
        catalogue['has_floor_plan'] = catalogue['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)
        
        return owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins
    except Exception as e:
        st.error(f"Error loading files: {e}. Ensure CSVs are in the root directory.")
        return [pd.DataFrame()] * 9

owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins = load_all_data()

# --- 3. SIDEBAR & TIME FILTERS ---
st.sidebar.title("📊 Control Center")
# Defaulting to Jan 2026 based on your data snippets
date_range = st.sidebar.date_input("Select Analysis Period", [datetime(2026, 1, 1), datetime(2026, 1, 14)])

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    # Logic for Previous Period Comparison
    period_days = (end_dt - start_dt).days + 1
    prev_start = start_dt - timedelta(days=period_days)
    prev_end = start_dt - timedelta(days=1)
else:
    st.stop()

# Mapping helper
email_to_name = admins.set_index('Email')['First Name'].to_dict()
def get_name(val):
    if pd.isna(val): return "Unknown"
    v = str(val).strip().lower()
    for email, name in email_to_name.items():
        if str(email).lower() == v: return name
    return str(val)

# --- 4. TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Leaderboard", "📦 Supply", "🏠 SKU", "👤 Demand", "⚙️ Admin"])

# --- ADMIN: MANUAL INPUTS ---
with tab5:
    st.header("Admin Point Overrides")
    colA, colB = st.columns(2)
    tour_pts = colA.number_input("Points: Completed Tour", value=20)
    rating_pts = colB.number_input("Points: Google Rating", value=10)
    
    st.info("Assign manual counts for this period:")
    manual_entries = {}
    for person in admins['First Name'].unique():
        c1, c2 = st.columns(2)
        t = c1.number_input(f"Tours: {person}", 0, key=f"tour_{person}")
        r = c2.number_input(f"Ratings: {person}", 0, key=f"rate_{person}")
        manual_entries[person] = (t * tour_pts) + (r * rating_pts)

# --- LEADERBOARD LOGIC ---
with tab1:
    st.header("Individual Performance (Leaderboard)")
    
    # Filter Visits
    cv = visits[(visits['Scheduled Date'] >= start_dt) & (visits['Scheduled Date'] <= end_dt)]
    cv_comp = cv[cv['Status/Visit_status'] == '🏁 Completed']
    ci = inspections[(inspections['Inspected On'] >= start_dt) & (inspections['Inspected On'] <= end_dt)]
    
    # Point Calculation
    lo_data = []
    for phone, group in cv_comp.groupby('Lead Phone'):
        owner = get_name(group['Internal/LeadOwner'].iloc[0])
        # RV Logic: Completed visit before current period or multiple days in range
        past = visits[(visits['Lead Phone'] == phone) & (visits['Scheduled Date'] < start_dt) & (visits['Status/Visit Completed'] == True)]
        is_rv = not past.empty or group['Scheduled Date'].dt.date.nunique() > 1
        lo_data.append({'Person': owner, 'Pts': 7 if is_rv else 3})
    
    lo_pts = pd.DataFrame(lo_data).groupby('Person')['Pts'].sum() if lo_data else pd.Series(dtype=int)
    va_pts = cv_comp.groupby('WA_Msg/VA_Name').size() * 4
    ins_pts = ci.groupby('Inspected By').size() * 4
    ins_pts.index = [get_name(x) for x in ins_pts.index]
    
    leaderboard = []
    for p in admins['First Name'].unique():
        leaderboard.append({
            "Person": p,
            "Total Score": lo_pts.get(p,0) + va_pts.get(p,0) + ins_pts.get(p,0) + manual_entries.get(p,0),
            "Scheduled (MTD)": cv[cv['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Completed (MTD)": cv_comp[cv_comp['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Visits Managed": cv_comp[cv_comp['WA_Msg/VA_Name'] == p].shape[0],
            "Inspections": ci[ci['Inspected By'].apply(get_name) == p].shape[0]
        })
    
    st.dataframe(pd.DataFrame(leaderboard).sort_values("Total Score", ascending=False), use_container_width=True)

# --- SUPPLY TAB ---
with tab2:
    st.header("Supply Funnel & Churn")
    
    c_leads = len(owners[(owners['Internal/Created On'] >= start_dt) & (owners['Internal/Created On'] <= end_dt)])
    p_leads = len(owners[(owners['Internal/Created On'] >= prev_start) & (owners['Internal/Created On'] <= prev_end)])
    
    h_on = len(homes[(homes['Internal/Created On'] >= start_dt) & (homes['Internal/Created On'] <= end_dt)])
    p_h_on = len(homes[(homes['Internal/Created On'] >= prev_start) & (homes['Internal/Created On'] <= prev_end)])
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Owner Leads", c_leads, f"{c_leads - p_leads}")
    m2.metric("Homes Onboarded", h_on, f"{h_on - p_h_on}")
    
    churn_df = homes[(homes['Offboarding/DateTime'] >= start_dt) & (homes['Offboarding/DateTime'] <= end_dt)]
    regret = pd.to_numeric(churn_df[churn_df['Internal/Status'].isin(['On Hold', 'Sold'])]['Home/Ask_Price (lacs)'], errors='coerce').sum()
    m3.metric("Regrettable Loss", f"₹{regret}L")

# --- SKU TAB ---
with tab3:
    st.header("Inventory Distribution")
    col1, col2 = st.columns(2)
    
    live_count = len(homes[homes['Internal/Status'] == 'Live'])
    col1.metric("Live Inventory", live_count)
    
    fp_count = catalogue[catalogue['has_floor_plan'] == 1].shape[0]
    col2.metric("Verified Floor Plans", f"{fp_count} ({round(fp_count/max(live_count,1)*100,1)}%)")
    
    st.subheader("Top Performing Projects")
    top_projects = cv.groupby('Project').size().sort_values(ascending=False).head(10)
    st.bar_chart(top_projects)

# --- DEMAND TAB ---
with tab4:
    st.header("Demand Funnel")
    b_leads = buyers[(buyers['Dates/Created On'] >= start_dt) & (buyers['Dates/Created On'] <= end_dt)]
    
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [b_leads['Contact/Phone'].nunique(), cv['Lead Phone'].nunique(), cv_comp['Lead Phone'].nunique()],
        textinfo = "value+percent initial",
        marker = {"color": ["#1f77b4", "#ff7f0e", "#2ca02c"]}
    ))
    st.plotly_chart(fig, use_container_width=True)