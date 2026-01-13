import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Jumbo Homes Dashboard", layout="wide")

# --- 2. EXACT FILENAME MAPPING ---
# These match the strings in your GitHub repository image
files = {
    'owners': 'Owners (17).csv',
    'calls': 'Periodic_Call_History_Report-12918973-2b5c-443f-ae0c-0104b8b1a339.csv',
    'visits': 'Visits (81).csv',
    'buyers': 'Buyers (48).csv',
    'inspections': 'home_inspection (15).csv',
    'homes': 'Homes (39).csv',
    'catalogue': 'home_catalogue (21).csv',
    'price_hist': 'b03be6.price-history-new.csv',
    'offers': 'c8bf87.offers.csv',
    'admins': 'Admins.csv'
}

# Diagnostic: Check for missing files before loading
missing = [f for f in files.values() if not os.path.exists(f)]
if missing:
    st.error(f"❌ Streamlit cannot find: {', '.join(missing)}")
    st.info("Files actually found in your GitHub repo root:")
    st.write(os.listdir('.'))
    st.stop()

# --- 3. DATA LOADING ---
def parse_dt(df, cols):
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True).dt.tz_localize(None)
    return df

@st.cache_data
def load_all_data():
    owners = parse_dt(pd.read_csv(files['owners']), ['Internal/Created On'])
    visits = parse_dt(pd.read_csv(files['visits']), ['Scheduled Date'])
    buyers = parse_dt(pd.read_csv(files['buyers']), ['Dates/Created On'])
    inspections = parse_dt(pd.read_csv(files['inspections']), ['Inspected On'])
    homes = parse_dt(pd.read_csv(files['homes']), ['Internal/Created On', 'Offboarding/DateTime'])
    catalogue = pd.read_csv(files['catalogue'])
    price_hist = parse_dt(pd.read_csv(files['price_hist']), ['date'])
    offers = parse_dt(pd.read_csv(files['offers']), ['Offer Date'])
    admins = pd.read_csv(files['admins'])
    
    # Logic: Project Name & Floor Plans
    visits['Project'] = visits['Homes_Visited'].str.split('_').str[0]
    catalogue['has_fp'] = catalogue['Media/Floor Plan'].apply(lambda x: 1 if (pd.notna(x) and 'https' in str(x)) else 0)
    
    return owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins

owners, visits, buyers, inspections, homes, catalogue, price_hist, offers, admins = load_all_data()

# --- 4. FILTERS & MAPPING ---
st.sidebar.title("📊 Control Center")
date_range = st.sidebar.date_input("Analysis Period", [datetime(2026, 1, 1), datetime(2026, 1, 14)])

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    # Period for % comparison
    delta = (end_dt - start_dt).days + 1
    p_start, p_end = start_dt - timedelta(days=delta), start_dt - timedelta(days=1)
else:
    st.stop()

email_to_name = admins.set_index('Email')['First Name'].to_dict()
def get_name(val):
    if pd.isna(val): return "Unknown"
    v = str(val).strip().lower()
    for email, name in email_to_name.items():
        if str(email).lower() == v: return name
    return str(val)

# --- 5. DASHBOARD TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Leaderboard", "📦 Supply", "🏠 SKU", "👤 Demand", "⚙️ Admin"])

with tab5:
    st.header("Admin Point Overrides")
    c1, c2 = st.columns(2)
    tour_pts = c1.number_input("Points: Completed Tour", value=20)
    rate_pts = c2.number_input("Points: Google Rating", value=10)
    
    manual_entries = {}
    for person in admins['First Name'].unique():
        col_t, col_r = st.columns(2)
        t = col_t.number_input(f"Tours: {person}", 0, key=f"t_{person}")
        r = col_r.number_input(f"Ratings: {person}", 0, key=f"r_{person}")
        manual_entries[person] = (t * tour_pts) + (r * rate_pts)

with tab1:
    st.header("Individual Performance")
    cv = visits[(visits['Scheduled Date'] >= start_dt) & (visits['Scheduled Date'] <= end_dt)]
    cv_comp = cv[cv['Status/Visit Completed'] == True]
    ci = inspections[(inspections['Inspected On'] >= start_dt) & (inspections['Inspected On'] <= end_dt)]
    
    # Points Logic (Per Visitor)
    lo_data = []
    for phone, group in cv_comp.groupby('Lead Phone'):
        owner = get_name(group['Internal/LeadOwner'].iloc[0])
        # RV check: Visit before start_dt OR multi-date in current range
        past = visits[(visits['Lead Phone'] == phone) & (visits['Scheduled Date'] < start_dt) & (visits['Status/Visit Completed'] == True)]
        is_rv = not past.empty or group['Scheduled Date'].dt.date.nunique() > 1
        lo_data.append({'Person': owner, 'Pts': 7 if is_rv else 3})
    
    lo_pts = pd.DataFrame(lo_data).groupby('Person')['Pts'].sum() if lo_data else pd.Series(dtype=int)
    va_pts = cv_comp.groupby('WA_Msg/VA_Name').size() * 4
    ins_pts = ci.groupby('Inspected By').size() * 4
    ins_pts.index = [get_name(x) for x in ins_pts.index]
    
    leader_df = []
    for p in admins['First Name'].unique():
        score = lo_pts.get(p,0) + va_pts.get(p,0) + ins_pts.get(p,0) + manual_entries.get(p,0)
        leader_df.append({
            "Person": p, "Total Points": score,
            "Sched (LO)": cv[cv['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Comp (LO)": cv_comp[cv_comp['Internal/LeadOwner'].apply(get_name) == p].shape[0],
            "Visits Managed": cv_comp[cv_comp['WA_Msg/VA_Name'] == p].shape[0],
            "Inspections": ci[ci['Inspected By'].apply(get_name) == p].shape[0]
        })
    st.table(pd.DataFrame(leader_df).sort_values("Total Points", ascending=False))

with tab2:
    st.header("Supply Funnel")
    c_leads = len(owners[(owners['Internal/Created On'] >= start_dt) & (owners['Internal/Created On'] <= end_dt)])
    p_leads = len(owners[(owners['Internal/Created On'] >= p_start) & (owners['Internal/Created On'] <= p_end)])
    
    h_on = len(homes[(homes['Internal/Created On'] >= start_dt) & (homes['Internal/Created On'] <= end_dt)])
    p_h_on = len(homes[(homes['Internal/Created On'] >= p_start) & (homes['Internal/Created On'] <= p_end)])
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Owner Leads", c_leads, f"{c_leads - p_leads}")
    m2.metric("Homes Onboarded", h_on, f"{h_on - p_h_on}")
    
    loss_curr = homes[(homes['Offboarding/DateTime'] >= start_dt) & (homes['Offboarding/DateTime'] <= end_dt)]
    regret = pd.to_numeric(loss_curr[loss_curr['Internal/Status'].isin(['On Hold', 'Sold'])]['Home/Ask_Price (lacs)'], errors='coerce').sum()
    m3.metric("Regrettable Loss", f"₹{regret}L")

with tab3:
    st.header("SKU Analysis")
    live = len(homes[homes['Internal/Status'] == 'Live'])
    fp = catalogue[catalogue['has_fp'] == 1].shape[0]
    st.metric("Live Homes", live)
    st.metric("Verified Floor Plans", f"{fp} ({round(fp/max(live,1)*100,1)}%)")
    st.subheader("Top Projects")
    st.bar_chart(cv.groupby('Project').size().sort_values(ascending=False).head(10))

with tab4:
    st.header("Demand Funnel")
    b_leads = buyers[(buyers['Dates/Created On'] >= start_dt) & (buyers['Dates/Created On'] <= end_dt)]
    fig = go.Figure(go.Funnel(
        y = ["Buyer Leads", "Visitors Scheduled", "Visitors Completed"],
        x = [b_leads['Contact/Phone'].nunique(), cv['Lead Phone'].nunique(), cv_comp['Lead Phone'].nunique()],
        textinfo = "value+percent initial"
    ))
    st.plotly_chart(fig, use_container_width=True)
