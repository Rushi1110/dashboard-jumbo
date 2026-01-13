import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Jumbo Homes | Internal Tool", layout="wide")

# --- 2. DATA LOADING & SIMPLIFIED MAPPING ---
def parse_dt(df, cols):
    for col in cols:
        if col in df.columns:
            # utc=True and tz_localize(None) ensures no naive/aware comparison crashes
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True).dt.tz_localize(None)
    return df

@st.cache_data
def load_all_data():
    # Simplified names as per your requirement
    files = {
        'owners': 'Owners.csv',
        'visits': 'Visits.csv',
        'buyers': 'Buyers.csv',
        'inspections': 'home_inspection.csv',
        'homes': 'Homes.csv',
        'catalogue': 'home_catalogue.csv',
        'price_hist': 'price-history-new.csv',
        'offers': 'offers.csv',
        'admins': 'Admins.csv',
        'calls': 'Call_history.csv'
    }

    # Diagnostic: Check if files exist
    missing = [f for f in files.values() if not os.path.exists(f)]
    if missing:
        st.error(f"❌ Missing Files: {', '.join(missing)}")
        st.stop()

    owners = parse_dt(pd.read_csv(files['owners']), ['Internal/Created On'])
    visits = parse_dt(pd.read_csv(files['visits']), ['Scheduled Date'])
    buyers = parse_dt(pd.read_csv(files['buyers']), ['Dates/Created On'])
    inspections = parse_dt(pd.read_csv(files['inspections']), ['Inspected On'])
    homes = parse_dt(pd.read_csv(files['homes']), ['Internal/Created On', 'Offboarding/DateTime'])
    catalogue = pd.read_csv(files['catalogue'])
    price_hist = parse_dt(pd.read_csv(files['price_hist']), ['date'])
    offers = parse_dt(pd.read_csv(files['offers']), ['Offer Date'])
    admins = pd.read_csv(files['admins'])
    
    # Pre-processing
    visits['Project'] = visits['Homes_Visited'].str.split('_').str[0]
    catalogue['has_fp'] = catalogue['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)
    
    return owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins

owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins = load_all_data()

# --- 3. FILTERS & MAPPING ---
st.sidebar.title("📊 Control Center")
# Set default to Jan 2026 for initial view
date_range = st.sidebar.date_input("Analysis Period", [datetime(2026, 1, 1), datetime(2026, 1, 14)])

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    delta = (end_dt - start_dt).days + 1
    p_start, p_end = start_dt - timedelta(days=delta), start_dt - timedelta(days=1)
else:
    st.stop()

# Helper for Lead Owner / VA mapping
email_to_name = admins.set_index('Email')['First Name'].to_dict()
def get_name(val):
    if pd.isna(val): return "Unknown"
    v = str(val).strip().lower()
    for email, name in email_to_name.items():
        if str(email).lower() == v: return name
    return str(val)

# --- 4. TABS ---
tab_lead, tab_supply, tab_sku, tab_demand, tab_admin = st.tabs([
    "🏆 Leaderboard", "📦 Supply", "🏠 SKU", "👤 Demand", "⚙️ Admin"
])

# Admin Tab for Manual Overrides
with tab_admin:
    st.header("Point Overrides")
    c1, c2 = st.columns(2)
    tour_pts = c1.number_input("Pts: Tour", value=20)
    rate_pts = c2.number_input("Pts: Rating", value=10)
    manual_data = {}
    for person in admins['First Name'].unique():
        col1, col2 = st.columns(2)
        t = col1.number_input(f"Tours: {person}", 0, key=f"t_{person}")
        r = col2.number_input(f"Ratings: {person}", 0, key=f"r_{person}")
        manual_data[person] = (t * tour_pts) + (r * rate_pts)

# Leaderboard Logic
with tab_lead:
    cv = visits[(visits['Scheduled Date'] >= start_dt) & (visits['Scheduled Date'] <= end_dt)]
    cv_comp = cv[cv['Status/Visit Completed'] == True]
    ci = inspections[(inspections['Inspected On'] >= start_dt) & (inspections['Inspected On'] <= end_dt)]
    
    lo_pts_list = []
    for phone, group in cv_comp.groupby('Lead Phone'):
        owner = get_name(group['Internal/LeadOwner'].iloc[0])
        past = visits[(visits['Lead Phone'] == phone) & (visits['Scheduled Date'] < start_dt) & (visits['Status/Visit Completed'] == True)]
        is_rv = not past.empty or group['Scheduled Date'].dt.date.nunique() > 1
        lo_pts_list.append({'Person': owner, 'Pts': 7 if is_rv else 3})
    
    lo_pts = pd.DataFrame(lo_pts_list).groupby('Person')['Pts'].sum() if lo_pts_list else pd.Series(dtype=int)
    va_pts = cv_comp.groupby('WA_Msg/VA_Name').size() * 4
    ins_pts = ci.groupby('Inspected By').size() * 4
    ins_pts.index = [get_name(x) for x in ins_pts.index]
    
    leader_df = []
    for p in admins['First Name'].unique():
        total = lo_pts.get(p,0) + va_pts.get(p,0) + ins_pts.get(p,0) + manual_data.get(p,0)
        leader_df.append({
            "Person": p, "Score": total,
            "Sched": cv[cv['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Comp": cv_comp[cv_comp['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Managed": cv_comp[cv_comp['WA_Msg/VA_Name'] == p].shape[0]
        })
    st.table(pd.DataFrame(leader_df).sort_values("Score", ascending=False))

# Supply Tab
with tab_supply:
    curr_o = len(owners[(owners['Internal/Created On'] >= start_dt) & (owners['Internal/Created On'] <= end_dt)])
    prev_o = len(owners[(owners['Internal/Created On'] >= p_start) & (owners['Internal/Created On'] <= p_end)])
    curr_h = len(homes[(homes['Internal/Created On'] >= start_dt) & (homes['Internal/Created On'] <= end_dt)])
    prev_h = len(homes[(homes['Internal/Created On'] >= p_start) & (homes['Internal/Created On'] <= p_end)])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Owner Leads", curr_o, f"{curr_o - prev_o}")
    col2.metric("Homes Onboarded", curr_h, f"{curr_h - prev_h}")
    
    loss = homes[(homes['Offboarding/DateTime'] >= start_dt) & (homes['Offboarding/DateTime'] <= end_dt)]
    regret = pd.to_numeric(loss[loss['Internal/Status'].isin(['On Hold', 'Sold'])]['Home/Ask_Price (lacs)'], errors='coerce').sum()
    col3.metric("Regrettable Loss", f"₹{regret}L")

# SKU Tab
with tab_sku:
    live = len(homes[homes['Internal/Status'] == 'Live'])
    fp = catalogue[catalogue['has_fp'] == 1].shape[0]
    st.metric("Live Inventory", live)
    st.metric("Verified Floor Plans", f"{fp} ({round(fp/max(live,1)*100,1)}%)")
    st.bar_chart(cv.groupby('Project').size().sort_values(ascending=False).head(10))

# Demand Tab
with tab_demand:
    b_leads = buyers[(buyers['Dates/Created On'] >= start_dt) & (buyers['Dates/Created On'] <= end_dt)]
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [b_leads['Contact/Phone'].nunique(), cv['Lead Phone'].nunique(), cv_comp['Lead Phone'].nunique()],
        textinfo = "value+percent initial"
    ))
    st.plotly_chart(fig, use_container_width=True)
