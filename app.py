# Project Continuum - Amazon Global Logistics Digital Platform
# v2.2 - Navigation fix + full mock-ups + SIM/RIVER quote flow

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3, json, os, uuid
from datetime import datetime, date, timedelta
from io import BytesIO

st.set_page_config(page_title="Continuum | AGL", page_icon="🌐", layout="wide", initial_sidebar_state="expanded")

USERS = {
    "agladmin": {"password": "continuum2026", "role": "internal", "scac": None,   "display": "AGL Admin"},
    "arvy":     {"password": "arvy2026",       "role": "carrier",  "scac": "ARVY", "display": "Arrive Logistics"},
    "atmi":     {"password": "atmi2026",       "role": "carrier",  "scac": "ATMI", "display": "Cargomatic"},
    "hrrd":     {"password": "hrrd2026",       "role": "carrier",  "scac": "HRRD", "display": "HUDD/Maersk"},
    "rkne":     {"password": "rkne2026",       "role": "carrier",  "scac": "RKNE", "display": "Road One"},
    "tghe":     {"password": "tghe2026",       "role": "carrier",  "scac": "TGHE", "display": "Tighe Logistics"},
    "gbdv":     {"password": "gbdv2026",       "role": "carrier",  "scac": "GBDV", "display": "Glovis"},
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuum.db")

SHEET_CFG = {
    "Avail-Pending OA":      {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": "Carrier"},
    "OA - Missing Del Appt": {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": "Carrier"},
    "Completed Pickups":     {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": "Carrier"},
    "Delivery Appointments": {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": "Carrier"},
    "Completed Deliveries":  {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": None},
    "Delivery Plan":         {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": None},
    "On Water":              {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": None},
    "Demurrage":             {"container_cols": ["Container","Container ID","Loaded Container","Container #"], "carrier_col": "Carrier"},
}

DEFAULTS = {
    "auth": False, "page": "landing", "role": "external",
    "scac": None, "username": None, "display_name": "Guest",
    "quote_tickets": [], "last_ticket": None, "track_query": "", "view_as_scac": None, "sub_refresh": 0,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

def nav(page):
    st.session_state.page = page
    st.rerun()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS dbr_containers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sheet_name TEXT, container_id TEXT,
        carrier TEXT, status_label TEXT, row_data TEXT, upload_batch TEXT, uploaded_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS delivery_report (
        id INTEGER PRIMARY KEY AUTOINCREMENT, container_id TEXT, asn_load_number TEXT,
        destination_fc TEXT, actual_fc TEXT, actual_delivery_dt TEXT, supplier TEXT,
        po_number TEXT, part_number TEXT, part_description TEXT, quantity REAL,
        carrier TEXT, region TEXT, uploaded_at TEXT,
        UNIQUE(container_id, asn_load_number))""")
    c.execute("""CREATE TABLE IF NOT EXISTS dbr_upload_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, file_name TEXT,
        sheets_loaded INTEGER, rows_loaded INTEGER, uploaded_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS carrier_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_date TEXT, carrier_scac TEXT, container_id TEXT,
        current_status TEXT, current_bridge TEXT, prior_bridge TEXT,
        planned_pu_date TEXT, notes TEXT,
        is_submitted INTEGER DEFAULT 0, submitted_at TEXT,
        UNIQUE(submission_date, carrier_scac, container_id))""")
    conn.commit(); conn.close()

init_db()

_t = date.today()

MOCK_SHIPMENTS = pd.DataFrame([
    {"Container":"MSCU1234567","Origin":"Shanghai, CN",  "Dest FC":"RIC6","Carrier":"ARVY","Status":"Available",        "ETA":str(_t+timedelta(1)), "Vessel":"EVER GIVEN",         "Type":"40HC"},
    {"Container":"HLXU8765432","Origin":"Yantian, CN",   "Dest FC":"ILM1","Carrier":"HRRD","Status":"Delivery Appt Set","ETA":str(_t+timedelta(2)), "Vessel":"MSC OSCAR",          "Type":"45HC"},
    {"Container":"CMAU3345678","Origin":"Ningbo, CN",    "Dest FC":"RIC6","Carrier":"ARVY","Status":"In Transit",       "ETA":str(_t+timedelta(7)), "Vessel":"COSCO UNIVERSE",     "Type":"40HC"},
    {"Container":"TCKU9871234","Origin":"Busan, KR",     "Dest FC":"LAX9","Carrier":"ATMI","Status":"On Water",         "ETA":str(_t+timedelta(14)),"Vessel":"HMM ALGECIRAS",      "Type":"45HC"},
    {"Container":"MRKU4456789","Origin":"Tokyo, JP",     "Dest FC":"BOS7","Carrier":"RKNE","Status":"Pending OA",       "ETA":str(_t+timedelta(3)), "Vessel":"MSC GULSUN",         "Type":"40HC"},
    {"Container":"EISU7893456","Origin":"Shanghai, CN",  "Dest FC":"ILM1","Carrier":"HRRD","Status":"Completed",        "ETA":str(_t-timedelta(2)), "Vessel":"EVER ACE",           "Type":"40HC"},
    {"Container":"FCIU2345678","Origin":"Qingdao, CN",   "Dest FC":"RIC6","Carrier":"ARVY","Status":"In Transit",       "ETA":str(_t+timedelta(9)), "Vessel":"CMA CGM MARCO POLO", "Type":"45HC"},
    {"Container":"OOLU6789012","Origin":"Guangzhou, CN", "Dest FC":"BOS7","Carrier":"TGHE","Status":"Available",        "ETA":str(_t),              "Vessel":"EVER ALOT",          "Type":"40HC"},
    {"Container":"PONU4567890","Origin":"Kaohsiung, TW", "Dest FC":"EWR4","Carrier":"RKNE","Status":"On Water",         "ETA":str(_t+timedelta(11)),"Vessel":"MSC LORETO",         "Type":"40HC"},
    {"Container":"SUDU8901234","Origin":"Xiamen, CN",    "Dest FC":"RIC6","Carrier":"ATMI","Status":"Demurrage Risk",   "ETA":str(_t-timedelta(1)), "Vessel":"OOCL EUROPE",        "Type":"45HC"},
    {"Container":"GLVU1122334","Origin":"Incheon, KR",   "Dest FC":"BOS7","Carrier":"GBDV","Status":"On Water",         "ETA":str(_t+timedelta(12)),"Vessel":"GLOVIS CORONA",      "Type":"40HC"},
    {"Container":"GLVU5566778","Origin":"Busan, KR",     "Dest FC":"EWR4","Carrier":"GBDV","Status":"Available",        "ETA":str(_t+timedelta(1)), "Vessel":"GLOVIS SUPREME",     "Type":"45HC"},
])

MOCK_TRACK_DB = {
    "MSCU1234567": {"vessel":"EVER GIVEN","origin":"Shanghai, CN","destination":"Richmond, VA — RIC6","carrier":"ARVY","container_type":"40HC",
        "stages":[("Origin Gate-In","Oct 01, 2026","done"),("Vessel Departed","Oct 04, 2026","done"),("Port Discharged","Oct 18, 2026","done"),("Available for Pickup","Oct 19, 2026","active"),("Out for Delivery","TBD","pending"),("Delivered to FC","TBD","pending")]},
    "HLXU8765432": {"vessel":"MSC OSCAR","origin":"Yantian, CN","destination":"Wilmington, NC — ILM1","carrier":"HRRD","container_type":"45HC",
        "stages":[("Origin Gate-In","Oct 05, 2026","done"),("Vessel Departed","Oct 08, 2026","done"),("Port Discharged","Oct 17, 2026","done"),("Available for Pickup","Oct 18, 2026","done"),("Out for Delivery","Oct 19, 2026","active"),("Delivered to FC","TBD","pending")]},
    "CMAU3345678": {"vessel":"COSCO UNIVERSE","origin":"Ningbo, CN","destination":"Richmond, VA — RIC6","carrier":"ARVY","container_type":"40HC",
        "stages":[("Origin Gate-In","Oct 10, 2026","done"),("Vessel Departed","Oct 12, 2026","done"),("Port Discharged","TBD","pending"),("Available for Pickup","TBD","pending"),("Out for Delivery","TBD","pending"),("Delivered to FC","TBD","pending")]},
}

MOCK_DELIVERY_DF = pd.DataFrame([
    {"container_id":"MSCU1234567","asn_load_number":"ASN-001234","destination_fc":"RIC6","actual_fc":"RIC6","actual_delivery_dt":str(_t-timedelta(5)),"supplier":"Samsung Electronics","po_number":"PO-9872341","part_number":"ARM-ROBOT-001","part_description":"Robotic Arm Assembly","quantity":4,"carrier":"ARVY","region":"East"},
    {"container_id":"HLXU8765432","asn_load_number":"ASN-001235","destination_fc":"ILM1","actual_fc":"ILM1","actual_delivery_dt":str(_t-timedelta(3)),"supplier":"Fanuc Corp","po_number":"PO-9872342","part_number":"CTRL-UNIT-007","part_description":"Controller Unit v7","quantity":2,"carrier":"HRRD","region":"Southeast"},
    {"container_id":"CMAU3345678","asn_load_number":"ASN-001236","destination_fc":"RIC6","actual_fc":"RIC6","actual_delivery_dt":str(_t-timedelta(1)),"supplier":"KUKA Robotics","po_number":"PO-9872343","part_number":"SENSOR-PKG-12","part_description":"Sensor Package Set","quantity":10,"carrier":"ARVY","region":"East"},
    {"container_id":"EISU7893456","asn_load_number":"ASN-001237","destination_fc":"ILM1","actual_fc":"ILM1","actual_delivery_dt":str(_t-timedelta(2)),"supplier":"ABB Ltd","po_number":"PO-9872344","part_number":"DRIVE-MOD-04","part_description":"Drive Module 04","quantity":6,"carrier":"HRRD","region":"Southeast"},
    {"container_id":"TCKU9871234","asn_load_number":"ASN-001238","destination_fc":"LAX9","actual_fc":"LAX9","actual_delivery_dt":str(_t-timedelta(7)),"supplier":"Yaskawa Electric","po_number":"PO-9872345","part_number":"MOTOR-ASSY-02","part_description":"Motor Assembly 02","quantity":8,"carrier":"ATMI","region":"West"},
    {"container_id":"OOLU6789012","asn_load_number":"ASN-001239","destination_fc":"BOS7","actual_fc":"BOS7","actual_delivery_dt":str(_t-timedelta(4)),"supplier":"Omron Corp","po_number":"PO-9872346","part_number":"CAM-MODULE-09","part_description":"Vision Camera Module","quantity":12,"carrier":"TGHE","region":"Northeast"},
    {"container_id":"GLVU5566778","asn_load_number":"ASN-001240","destination_fc":"EWR4","actual_fc":"EWR4","actual_delivery_dt":str(_t-timedelta(1)),"supplier":"Hyundai Mobis","po_number":"PO-9872347","part_number":"LIDAR-UNIT-03","part_description":"LiDAR Sensor Unit","quantity":5,"carrier":"GBDV","region":"Northeast"},
])

MOCK_QUOTE_HISTORY = [
    {"Ticket ID":"RVR-AGL-20261015-A3F2B","Route":"RIVER","Origin":"Shanghai, CN","Dest FC":"RIC6","Type":"40HC","TEUs":2,"Service":"Standard","Priority":"Normal","Status":"Quote Ready","Submitted":"2026-10-15 14:22 UTC"},
    {"Ticket ID":"SIM-AGL-20261012-C7D1E","Route":"SIM",  "Origin":"Yantian, CN", "Dest FC":"ILM1","Type":"45HC","TEUs":1,"Service":"Expedited","Priority":"High",  "Status":"Approved",    "Submitted":"2026-10-12 09:41 UTC"},
    {"Ticket ID":"RVR-AGL-20261008-F4A9C","Route":"RIVER","Origin":"Ningbo, CN",  "Dest FC":"BOS7","Type":"40HC","TEUs":4,"Service":"Standard","Priority":"Normal","Status":"Carrier Outreach","Submitted":"2026-10-08 11:15 UTC"},
]

MOCK_DBR = {
    "Avail-Pending OA": pd.DataFrame([
        {"Container":"MSCU1234567","Carrier":"ARVY","Origin Port":"Norfolk","Available Date":str(_t-timedelta(1)),"Current Bridge":"Awaiting driver","Prior Day's Bridge":"Terminal released","Planned PU Date":str(_t+timedelta(1)),"Notes":""},
        {"Container":"MRKU4456789","Carrier":"RKNE","Origin Port":"Norfolk","Available Date":str(_t),"Current Bridge":"OA scheduled","Prior Day's Bridge":"Available","Planned PU Date":str(_t+timedelta(2)),"Notes":"Priority"},
        {"Container":"OOLU6789012","Carrier":"TGHE","Origin Port":"Savannah","Available Date":str(_t),"Current Bridge":"Pending driver","Prior Day's Bridge":"Available","Planned PU Date":str(_t+timedelta(1)),"Notes":""},
        {"Container":"GLVU5566778","Carrier":"GBDV","Origin Port":"Newark","Available Date":str(_t+timedelta(1)),"Current Bridge":"Vessel arriving","Prior Day's Bridge":"On water","Planned PU Date":str(_t+timedelta(2)),"Notes":""},
    ]),
    "OA - Missing Del Appt": pd.DataFrame([
        {"Container":"CMAU3345678","Carrier":"ARVY","Origin Port":"Norfolk","OA Date":str(_t-timedelta(1)),"Current Bridge":"FC not responding","Prior Day's Bridge":"Appt requested","Notes":"Follow up needed"},
        {"Container":"FCIU2345678","Carrier":"ARVY","Origin Port":"Norfolk","OA Date":str(_t),"Current Bridge":"Rescheduling","Prior Day's Bridge":"Orig appt cancelled","Notes":""},
    ]),
    "Completed Pickups": pd.DataFrame([
        {"Container":"HLXU8765432","Carrier":"HRRD","Pickup Date":str(_t-timedelta(1)),"Origin Port":"Wilmington","Destination FC":"ILM1","Current Bridge":"En route","Prior Day's Bridge":"Picked up","Planned PU Date":str(_t-timedelta(1)),"Notes":""},
    ]),
    "Delivery Appointments": pd.DataFrame([
        {"Container":"CMAU3345678","Carrier":"ARVY","Appt Date":str(_t+timedelta(1)),"Appt Time":"09:30","Destination FC":"RIC6","Status":"Confirmed"},
        {"Container":"HLXU8765432","Carrier":"HRRD","Appt Date":str(_t+timedelta(1)),"Appt Time":"07:30","Destination FC":"ILM1","Status":"Confirmed"},
    ]),
    "Completed Deliveries": pd.DataFrame([
        {"Container":"EISU7893456","Delivery Date":str(_t-timedelta(2)),"Destination FC":"ILM1","PO Number":"PO-9872344","Quantity":6},
        {"Container":"TCKU9871234","Delivery Date":str(_t-timedelta(7)),"Destination FC":"LAX9","PO Number":"PO-9872345","Quantity":8},
        {"Container":"OOLU6789012","Delivery Date":str(_t-timedelta(4)),"Destination FC":"BOS7","PO Number":"PO-9872346","Quantity":12},
        {"Container":"GLVU5566778","Delivery Date":str(_t-timedelta(1)),"Destination FC":"EWR4","PO Number":"PO-9872347","Quantity":5},
    ]),
    "Delivery Plan": pd.DataFrame([
        {"Container":"TCKU9871234","Vessel":"HMM ALGECIRAS","ETD":str(_t+timedelta(5)),"ETA":str(_t+timedelta(14)),"Destination FC":"BOS7","Type":"40HC"},
        {"Container":"FCIU2345678","Vessel":"CMA CGM MARCO POLO","ETD":str(_t+timedelta(2)),"ETA":str(_t+timedelta(9)),"Destination FC":"RIC6","Type":"45HC"},
        {"Container":"PONU4567890","Vessel":"MSC LORETO","ETD":str(_t+timedelta(3)),"ETA":str(_t+timedelta(11)),"Destination FC":"EWR4","Type":"40HC"},
    ]),
    "On Water": pd.DataFrame([
        {"Container":"MSCU1234567","Vessel":"EVER GIVEN","Origin":"Shanghai","Last Port":"Ningbo","ETA":str(_t+timedelta(6)),"Destination FC":"RIC6"},
        {"Container":"TCKU9871234","Vessel":"HMM ALGECIRAS","Origin":"Busan","Last Port":"Busan","ETA":str(_t+timedelta(14)),"Destination FC":"LAX9"},
        {"Container":"CMAU3345678","Vessel":"COSCO UNIVERSE","Origin":"Ningbo","Last Port":"Long Beach","ETA":str(_t+timedelta(7)),"Destination FC":"RIC6"},
    ]),
    "Demurrage": pd.DataFrame([
        {"Container":"MRKU4456789","Carrier":"RKNE","Port":"Norfolk","Free Days Remaining":2,"Daily Rate":"$350","Accrued":"$700","Notes":"Expedite OA"},
        {"Container":"SUDU8901234","Carrier":"ATMI","Port":"Savannah","Free Days Remaining":0,"Daily Rate":"$400","Accrued":"$1,600","Notes":"Urgent — escalate"},
    ]),
}

st.markdown("""<style>
#MainMenu{visibility:hidden;}footer{visibility:hidden;}header{visibility:hidden;}
.block-container{padding-top:1rem!important;}
.stButton>button{border-radius:4px;font-weight:600;}
.int-badge{background:#1a472a;color:#fff;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;display:inline-block;margin-bottom:10px;}
.carr-badge{background:#1a3a5c;color:#fff;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;display:inline-block;margin-bottom:10px;}
.preview-badge{background:#4a2a00;color:#fff;padding:4px 12px;border-radius:4px;font-size:12px;font-weight:600;display:inline-block;margin-bottom:10px;}
</style>""", unsafe_allow_html=True)

def int_badge():
    st.markdown('<span class="int-badge">&#x1F512; Internal &#x2014; AGL Admin</span>', unsafe_allow_html=True)

def carr_badge():
    st.markdown(f'<span class="carr-badge">&#x1F69B; {st.session_state.display_name} ({st.session_state.scac})</span>', unsafe_allow_html=True)

def preview_badge(label):
    st.markdown(f'<span class="preview-badge">&#x1F441; Previewing: {label}</span>', unsafe_allow_html=True)

def sidebar_nav():
    role = st.session_state.role
    with st.sidebar:
        st.markdown(f"**{st.session_state.display_name}**")
        st.caption("Amazon Global Logistics")
        st.markdown('<span style="background:#7a3800;color:#ffd580;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">BETA — PROTOTYPE</span>', unsafe_allow_html=True)
        st.divider()
        items = [("Home","landing"),("Shipments","shipments"),("Track & Trace","track"),("Get a Quote","quote")]
        if role == "internal":
            items += [("Dashboard","dashboard"),("DBR Dashboard","dbr_dashboard"),("Delivery Report","delivery_report")]
        else:
            items = [("Daily Submission","carrier_portal"),("Delivery Report","delivery_report"),("Track & Trace","track"),("Get a Quote","quote")]
        for label, pg in items:
            if st.button(label, key=f"snav_{pg}", use_container_width=True):
                nav(pg)
        st.divider()
        # Carrier view selector — always visible for internal users
        if role == "internal":
            st.markdown("**View as Carrier**")
            carrier_options = {u: v for u, v in USERS.items() if v["role"] == "carrier"}
            view_labels = ["Internal (All)"] + [f"{v['display']} ({v['scac']})" for v in carrier_options.values()]
            view_scacs  = [None] + [v["scac"] for v in carrier_options.values()]
            current_scac = st.session_state.get("view_as_scac")
            current_idx  = view_scacs.index(current_scac) if current_scac in view_scacs else 0
            sel = st.selectbox("", view_labels, index=current_idx, key="sidebar_view_as", label_visibility="collapsed")
            new_scac = view_scacs[view_labels.index(sel)]
            if new_scac != st.session_state.view_as_scac:
                st.session_state.view_as_scac = new_scac
                # Navigate to delivery report when a carrier is selected
                if new_scac:
                    st.session_state.page = "delivery_report"
                st.rerun()
            if st.session_state.view_as_scac:
                st.caption(f"Previewing: **{sel}**")
                if st.button("Back to Internal View", key="back_internal", use_container_width=True):
                    st.session_state.view_as_scac = None
                    st.rerun()
            st.divider()
        if st.button("Sign Out", key="signout", use_container_width=True):
            for k in list(DEFAULTS.keys()):
                st.session_state[k] = DEFAULTS[k]
            st.rerun()


# ── LOGIN ──────────────────────────────────────────────────────────────────────
def page_login():
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown("""<div style='text-align:center;padding:48px 0 28px;'>
          <div style='font-size:56px;'>&#x1F310;</div>
          <h1 style='font-size:34px;font-weight:700;margin:10px 0 4px;letter-spacing:-0.5px;'>Continuum</h1>
          <p style='color:#888;font-size:15px;margin:0;'>Amazon Global Logistics</p>
        </div>""", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            st.markdown("##### Sign in to continue")
            username = st.text_input("Username", placeholder="Username")
            password = st.text_input("Password", type="password", placeholder="Password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
        if submitted:
            u = username.strip().lower()
            if u in USERS and USERS[u]["password"] == password:
                st.session_state.auth         = True
                st.session_state.username     = u
                st.session_state.role         = USERS[u]["role"]
                st.session_state.scac         = USERS[u]["scac"]
                st.session_state.display_name = USERS[u]["display"]
                st.session_state.page         = "carrier_portal" if USERS[u]["role"] == "carrier" else "landing"
                st.rerun()
            else:
                st.error("Invalid credentials.")

# ── LANDING ────────────────────────────────────────────────────────────────────
def page_landing():
    sidebar_nav()
    if st.session_state.role == "internal":
        int_badge()
    st.markdown("""<div style='background:linear-gradient(135deg,#0B1623,#0D2137);border-radius:14px;
    padding:52px 40px;margin-bottom:28px;text-align:center;'>
      <h1 style='color:#fff;font-size:40px;font-weight:700;margin:0;'>Amazon Global Logistics</h1>
      <p style='color:#8899AA;font-size:17px;margin-top:10px;'>
        Connecting global supply chains with precision, speed, and visibility.
      </p>
    </div>""", unsafe_allow_html=True)
    st.info("**Beta prototype** — data shown is for demonstration purposes only. Persistence and live integrations are enabled on Amazon server deployment.", icon="ℹ️")
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Active Containers","2,408","+12 today")
    m2.metric("On Water","1,104","+3 voyages")
    m3.metric("Available / OA","287","-14 vs. yesterday")
    m4.metric("Deliveries This Wk","143","+8%")
    m5.metric("Demurrage Alerts","2",delta="-1",delta_color="inverse")
    st.divider()
    c1,c2,c3,c4 = st.columns(4)
    tiles = [("Track & Trace","Real-time container visibility.","track"),
             ("Get a Quote","Submit a procurement quote request.","quote"),
             ("Shipments","Manage and monitor active shipments.","shipments"),
             ("Dashboard","Internal operations overview.","dashboard")]
    for col,(title,desc,pg) in zip([c1,c2,c3,c4],tiles):
        with col:
            st.markdown(f"""<div style='background:#132133;border:1px solid #1E3A52;border-radius:10px;
            padding:20px;text-align:center;min-height:100px;'>
              <strong style='color:#fff;'>{title}</strong>
              <p style='color:#8899AA;font-size:12px;margin:6px 0 0;'>{desc}</p>
            </div>""", unsafe_allow_html=True)
            if st.button("Open", key=f"tile_{pg}", use_container_width=True):
                nav(pg)
    if st.session_state.role == "internal":
        st.divider()
        st.markdown("#### Recent Activity")
        activity = [
            {"Time":"Today 08:14","Event":"DBR file uploaded","Detail":"GVT Data WK42.xlsx — 8 sheets, 187 rows"},
            {"Time":"Today 07:30","Event":"Delivery confirmed","Detail":"HLXU8765432 to ILM1 (HRRD)"},
            {"Time":"Yesterday","Event":"Demurrage alert","Detail":"SUDU8901234 — 0 free days at Savannah"},
            {"Time":"Yesterday","Event":"Quote request","Detail":"RVR-AGL-20261018-D2C4A — routed to procurement"},
            {"Time":"Oct 17","Event":"New container added","Detail":"PONU4567890 — EWR4 via MSC LORETO"},
        ]
        st.dataframe(pd.DataFrame(activity), use_container_width=True, hide_index=True, height=220)

# ── SHIPMENTS ──────────────────────────────────────────────────────────────────
def page_shipments():
    sidebar_nav()
    if st.session_state.role == "internal":
        int_badge()
    st.title("Shipments")
    st.caption("Active container shipments — booking, status, and carrier assignments.")
    tab_all, tab_active, tab_water, tab_done = st.tabs(["All Shipments","Active / Available","On Water","Completed"])
    df = MOCK_SHIPMENTS.copy()
    with tab_all:
        c1,c2,c3 = st.columns([2,2,1])
        with c1:
            srch = st.text_input("Search", placeholder="Container ID...", key="sh_srch", label_visibility="collapsed")
        with c2:
            carr_opts = ["All Carriers"] + sorted(df["Carrier"].unique().tolist())
            c_sel = st.selectbox("Carrier", carr_opts, key="sh_carr", label_visibility="collapsed")
        with c3:
            st.metric("Total", len(df))
        fdf = df.copy()
        if srch: fdf = fdf[fdf["Container"].str.contains(srch,case=False,na=False)]
        if c_sel != "All Carriers": fdf = fdf[fdf["Carrier"]==c_sel]
        st.dataframe(fdf, use_container_width=True, hide_index=True, height=380)
    with tab_active:
        adf = df[df["Status"].isin(["Available","Delivery Appt Set","Pending OA","Demurrage Risk"])]
        m1,m2,m3 = st.columns(3)
        m1.metric("Available",      len(adf[adf["Status"]=="Available"]))
        m2.metric("Appt Set",       len(adf[adf["Status"]=="Delivery Appt Set"]))
        m3.metric("Demurrage Risk", len(adf[adf["Status"]=="Demurrage Risk"]))
        st.dataframe(adf, use_container_width=True, hide_index=True, height=320)
    with tab_water:
        wdf = df[df["Status"]=="On Water"]
        st.metric("On Water", len(wdf))
        st.dataframe(wdf, use_container_width=True, hide_index=True, height=200)
        fig = px.bar(wdf, x="Dest FC", color="Carrier", title="On-Water Volume by Destination FC",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
        st.plotly_chart(fig, use_container_width=True)
    with tab_done:
        ddf = df[df["Status"]=="Completed"]
        st.metric("Completed This Period", len(ddf))
        st.dataframe(ddf, use_container_width=True, hide_index=True)

# ── TRACK & TRACE ──────────────────────────────────────────────────────────────
def page_track():
    sidebar_nav()
    st.title("Track & Trace")
    st.caption("Enter a container number to check real-time status and milestone history.")
    demo_ids = list(MOCK_TRACK_DB.keys())
    c1,c2 = st.columns([3,1])
    with c1:
        query = st.text_input("Container", placeholder="e.g. MSCU1234567", key="track_inp", label_visibility="collapsed")
    with c2:
        if st.button("Track", type="primary", key="track_btn", use_container_width=True):
            st.session_state.track_query = query.strip().upper()
    st.caption(f"Demo containers: {', '.join(demo_ids)}")
    cid = st.session_state.get("track_query","")
    if not cid:
        return
    st.divider()
    data = MOCK_TRACK_DB.get(cid)
    if not data:
        st.warning(f"No tracking data found for **{cid}**.")
        return
    st.markdown(f"### Container: `{cid}`")
    i1,i2,i3,i4 = st.columns(4)
    i1.metric("Vessel",      data["vessel"])
    i2.metric("Origin",      data["origin"])
    i3.metric("Destination", data["destination"])
    i4.metric("Carrier",     data["carrier"])
    st.markdown("#### Milestone Progress")
    cols = st.columns(len(data["stages"]))
    for col,(stage,dt,state) in zip(cols,data["stages"]):
        if state=="done":    bg,icon,tc="#1a472a","V","#90ee90"
        elif state=="active":bg,icon,tc="#1a3a5c","*","#64b5f6"
        else:                bg,icon,tc="#1e1e1e","o","#666"
        col.markdown(f"""<div style='background:{bg};border-radius:8px;padding:14px 8px;text-align:center;'>
          <div style='color:{tc};font-size:16px;font-weight:700;'>{icon}</div>
          <div style='color:#fff;font-size:11px;font-weight:600;margin-top:4px;'>{stage}</div>
          <div style='color:#aaa;font-size:10px;margin-top:2px;'>{dt}</div>
        </div>""", unsafe_allow_html=True)

# ── QUOTE / SIM / RIVER ────────────────────────────────────────────────────────
def page_quote():
    sidebar_nav()
    st.title("Get a Quote")
    st.caption("Submit an ocean freight quote request routed to the AGL procurement team via RIVER or SIM.")
    tab_new, tab_hist = st.tabs(["New Request","Request History"])
    with tab_new:
        last = st.session_state.get("last_ticket")
        if last:
            st.success(f"Request submitted — **{last['ticket_id']}**")
            r1,r2,r3,r4 = st.columns(4)
            r1.metric("Ticket ID", last["ticket_id"])
            r2.metric("Route",     last["route"])
            r3.metric("Priority",  last["priority"])
            r4.metric("Status",    "Submitted")
            st.markdown("##### Request Flow")
            flow = ["Submitted","Procurement Review","Carrier Outreach","Quote Ready","Approved"]
            fcols = st.columns(len(flow))
            for i,(fc,fs) in enumerate(zip(fcols,flow)):
                bg = "#1a472a" if i==0 else "#1e2a3a"
                ic = "V" if i==0 else str(i+1)
                fc.markdown(f"""<div style='background:{bg};border-radius:8px;padding:12px;text-align:center;'>
                  <div style='color:#90ee90;font-weight:700;'>{ic}</div>
                  <div style='color:#fff;font-size:11px;margin-top:4px;'>{fs}</div>
                </div>""", unsafe_allow_html=True)
            if st.button("Submit Another Request", key="new_quote"):
                st.session_state.last_ticket = None
                st.rerun()
            return
        with st.form("quote_form"):
            st.markdown("#### Shipment Details")
            c1,c2 = st.columns(2)
            with c1:
                origin   = st.selectbox("Origin Port",     ["Shanghai, CN","Yantian, CN","Ningbo, CN","Qingdao, CN","Busan, KR","Tokyo, JP","Kaohsiung, TW","Xiamen, CN","Other"])
                dest     = st.selectbox("Destination FC",  ["RIC6 — Richmond, VA","ILM1 — Wilmington, NC","LAX9 — Los Angeles, CA","BOS7 — Boston, MA","EWR4 — Newark, NJ","Other"])
                ctype    = st.selectbox("Container Type",  ["40HC","45HC","20GP","40GP"])
                volume   = st.number_input("Volume (TEUs)", min_value=1, max_value=500, value=1)
            with c2:
                service   = st.selectbox("Service Level",    ["Standard (25-35 days)","Expedited (18-22 days)","Premium (14-17 days)"])
                commodity = st.text_input("Commodity",        placeholder="e.g. Robotic Components, Electronics")
                ready_dt  = st.date_input("Cargo Ready Date", value=_t+timedelta(7))
                target_rt = st.text_input("Target Rate (USD/FEU)", placeholder="Optional")
            st.markdown("#### Routing Preferences")
            c3,c4 = st.columns(2)
            with c3:
                pref_carriers = st.multiselect("Preferred Carriers", ["ARVY","ATMI","HRRD","RKNE","TGHE","GBDV","No Preference"], default=["No Preference"])
                routing_pref  = st.selectbox("Routing", ["Direct Only","Transshipment OK","No Preference"])
            with c4:
                priority = st.selectbox("Priority", ["Normal","High","Critical"])
                notes    = st.text_area("Notes / Special Requirements", height=88, placeholder="Hazmat, temperature control, special handling...")
            st.markdown("#### Route To")
            route_to = st.radio("", ["RIVER — Procurement Team","SIM — AGL Ops Ticket"], horizontal=True, label_visibility="collapsed")
            submitted = st.form_submit_button("Submit Request", type="primary", use_container_width=True)
        if submitted:
            if not commodity.strip():
                st.error("Commodity description is required.")
            else:
                prefix    = "RVR" if "RIVER" in route_to else "SIM"
                ticket_id = f"{prefix}-AGL-{_t.strftime('%Y%m%d')}-{str(uuid.uuid4())[:5].upper()}"
                ticket = {"ticket_id":ticket_id,"route":"RIVER" if "RIVER" in route_to else "SIM",
                          "origin":origin,"destination":dest,"container_type":ctype,"volume":volume,
                          "service":service,"commodity":commodity,"ready_date":str(ready_dt),
                          "priority":priority,"carriers":", ".join(pref_carriers),
                          "routing":routing_pref,"notes":notes,"status":"Submitted",
                          "submitted":datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
                st.session_state.quote_tickets.append(ticket)
                st.session_state.last_ticket = ticket
                st.rerun()
    with tab_hist:
        user_tickets = st.session_state.get("quote_tickets",[])
        all_tickets  = MOCK_QUOTE_HISTORY + [
            {"Ticket ID":t["ticket_id"],"Route":t["route"],"Origin":t["origin"],"Dest FC":t["destination"],
             "Type":t["container_type"],"TEUs":t["volume"],"Service":t["service"],"Priority":t["priority"],
             "Status":t["status"],"Submitted":t["submitted"]}
            for t in user_tickets
        ]
        df_t = pd.DataFrame(all_tickets)
        st.dataframe(df_t, use_container_width=True, hide_index=True, height=300)
        if not df_t.empty:
            sc = df_t["Status"].value_counts().reset_index(); sc.columns=["Status","Count"]
            fig = px.pie(sc, names="Status", values="Count", title="Requests by Status", hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)


# ── INTERNAL DASHBOARD ─────────────────────────────────────────────────────────
def page_dashboard():
    if st.session_state.role != "internal":
        st.error("Access denied."); return
    int_badge(); sidebar_nav()
    st.title("Internal Dashboard")
    tab_ov, tab_rep, tab_set = st.tabs(["Overview","Reports","Settings"])
    with tab_ov:
        conn = get_conn()
        dbr_live   = conn.execute("SELECT COUNT(*) FROM dbr_containers").fetchone()[0]
        dr_live    = conn.execute("SELECT COUNT(*) FROM delivery_report").fetchone()[0]
        last_batch = conn.execute("SELECT file_name FROM dbr_upload_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        total_cont = dbr_live if dbr_live > 0 else len(MOCK_SHIPMENTS)
        dr_count   = dr_live  if dr_live  > 0 else len(MOCK_DELIVERY_DF)
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Tracked Containers", total_cont)
        m2.metric("Delivery Records",   dr_count)
        m3.metric("Active Carriers",    5)
        m4.metric("Last DBR Upload", last_batch[0][:22] if last_batch else "Demo mode")
        st.divider()
        col_a,col_b = st.columns(2)
        with col_a:
            sd = MOCK_SHIPMENTS["Status"].value_counts().reset_index(); sd.columns=["Status","Count"]
            fig1 = px.bar(sd,x="Status",y="Count",title="Containers by Status",
                          color="Status",color_discrete_sequence=px.colors.qualitative.Set2)
            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#ccc",showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)
        with col_b:
            cd = MOCK_SHIPMENTS["Carrier"].value_counts().reset_index(); cd.columns=["Carrier","Containers"]
            fig2 = px.pie(cd,names="Carrier",values="Containers",title="Volume by Carrier",hole=0.35,
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
            st.plotly_chart(fig2, use_container_width=True)
        fcd = MOCK_SHIPMENTS["Dest FC"].value_counts().reset_index(); fcd.columns=["Dest FC","Containers"]
        fig3 = px.bar(fcd,x="Dest FC",y="Containers",title="Volume by Destination FC",color_discrete_sequence=["#1E88E5"])
        fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
        st.plotly_chart(fig3, use_container_width=True)
    with tab_rep:
        st.markdown("### Quick Links")
        r1,r2 = st.columns(2)
        with r1:
            st.markdown("**DBR Dashboard**"); st.caption("Daily Booking Report — all 8 sheets, carrier filters, export.")
            if st.button("Open DBR Dashboard", key="dash_dbr", use_container_width=True): nav("dbr_dashboard")
        with r2:
            st.markdown("**Delivery Report**"); st.caption("Delivery actuals by container, FC, and carrier.")
            if st.button("Open Delivery Report", key="dash_dr", use_container_width=True): nav("delivery_report")
    with tab_set:
        st.markdown("### Data Architecture")
        st.markdown('<span style="background:#7a3800;color:#ffd580;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:700;">DEMO MODE — SQLite</span>', unsafe_allow_html=True)
        st.markdown("##### Current State (Beta)")
        st.markdown("""
- **DB:** SQLite — ephemeral on Streamlit Cloud, resets on restart
- **Data entry:** Manual uploads (DBR Excel, Delivery Report Excel)
- **Carrier reporting:** Portal UI built; submissions stored in DB
        """)
        st.markdown("##### Target State (Amazon Servers)")
        st.markdown("""
- **DB:** Amazon RDS (PostgreSQL) — persistent, scalable
- **DBR pipeline:** `extract_dbr_attachments.py` (already running on QM) extended to push parsed data to S3 → RDS nightly
- **Delivery Report:** Automated pull from internal WMS/Oracle via Lambda → RDS
- **Carrier submissions:** Portal replaces email attachments entirely — carriers submit here, data lands in RDS in real time
- **Reminders:** Scheduled Lambda sends email/SES reminder to carriers at 1 PM MST if not yet submitted
- **Code change to go live:** Swap `DB_PATH` (SQLite) → `psycopg2` connection string (RDS) — one line
        """)
        st.divider()
        st.markdown("##### Carrier Submission Status — Today")
        conn = get_conn()
        today_subs = {}
        for u,v in USERS.items():
            if v["role"] == "carrier":
                sc = v["scac"]
                total_c   = len(CARRIER_CONTAINERS.get(sc,[]))
                submitted = conn.execute("SELECT COUNT(*) FROM carrier_submissions WHERE submission_date=? AND carrier_scac=? AND is_submitted=1",(str(_t),sc)).fetchone()[0]
                today_subs[v["display"]] = {"scac":sc,"submitted":submitted,"total":total_c}
        conn.close()
        if today_subs:
            rows = [{"Carrier":name,"SCAC":d["scac"],"Submitted":d["submitted"],"Total":d["total"],
                     "Status":"✅ Complete" if d["submitted"]==d["total"] and d["total"]>0 else ("⚠ Partial" if d["submitted"]>0 else "🔴 Not Started")}
                    for name,d in today_subs.items()]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Automated reminder sent at 1 PM MST to carriers with outstanding submissions (production feature).")
        st.divider()
        st.markdown("**Current admin:** agladmin | **Carriers:** ARVY, ATMI, HRRD, RKNE, TGHE, GBDV")

# ── DBR DASHBOARD ──────────────────────────────────────────────────────────────
def parse_dbr_excel(file_bytes, file_name):
    results, errors = {}, []
    try: xl = pd.ExcelFile(BytesIO(file_bytes))
    except Exception as e: return {}, [f"Cannot open file: {e}"]
    for sheet, cfg in SHEET_CFG.items():
        if sheet not in xl.sheet_names: errors.append(f"Sheet '{sheet}' not found — skipped."); continue
        try:
            df = pd.read_excel(xl, sheet_name=sheet, dtype=str).fillna("")
            container_col = next((c for c in cfg["container_cols"] if c in df.columns), None)
            rows = []
            for _,row in df.iterrows():
                rd = row.to_dict()
                cid    = str(rd.get(container_col,"")).strip() if container_col else ""
                carrier= str(rd.get(cfg["carrier_col"],"")).strip() if cfg["carrier_col"] else ""
                rows.append({"container_id":cid,"carrier":carrier,"row_data":rd})
            results[sheet] = rows
        except Exception as e: errors.append(f"Sheet '{sheet}' error: {e}")
    return results, errors

def store_dbr_batch(parsed, file_name, batch_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM dbr_containers")
    now = datetime.utcnow().isoformat()
    total_rows = sheets_loaded = 0
    for sheet_name,rows in parsed.items():
        for row in rows:
            c.execute("INSERT INTO dbr_containers (sheet_name,container_id,carrier,status_label,row_data,upload_batch,uploaded_at) VALUES (?,?,?,?,?,?,?)",
                (sheet_name,row["container_id"],row["carrier"],sheet_name,json.dumps(row["row_data"]),batch_id,now))
        total_rows += len(rows); sheets_loaded += 1
    c.execute("INSERT INTO dbr_upload_log (batch_id,file_name,sheets_loaded,rows_loaded,uploaded_at) VALUES (?,?,?,?,?)",
        (batch_id,file_name,sheets_loaded,total_rows,now))
    conn.commit(); conn.close()
    return sheets_loaded, total_rows

def load_dbr_sheet(sheet_name, carrier_filter=None):
    conn = get_conn()
    if carrier_filter:
        rows = conn.execute("SELECT row_data FROM dbr_containers WHERE sheet_name=? AND carrier=?",(sheet_name,carrier_filter)).fetchall()
    else:
        rows = conn.execute("SELECT row_data FROM dbr_containers WHERE sheet_name=?",(sheet_name,)).fetchall()
    conn.close()
    if not rows: return pd.DataFrame()
    return pd.DataFrame([json.loads(r[0]) for r in rows])

def last_upload_info():
    conn = get_conn()
    row = conn.execute("SELECT file_name,sheets_loaded,rows_loaded,uploaded_at FROM dbr_upload_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close(); return row

def page_dbr_dashboard():
    if st.session_state.role != "internal":
        st.error("Access denied."); return
    sidebar_nav()
    active_scac = st.session_state.get("view_as_scac")
    carrier_options = {u:v for u,v in USERS.items() if v["role"]=="carrier"}
    if active_scac:
        carrier_name = next((f"{v['display']} ({v['scac']})" for v in carrier_options.values() if v["scac"]==active_scac), active_scac)
        preview_badge(carrier_name)
    else:
        int_badge()
    st.title("DBR Dashboard")
    st.caption("Daily Booking Report — container tracking across all carriers and statuses.")
    if not active_scac:
        with st.expander("Upload DBR File", expanded=False):
            up = st.file_uploader("DBR Excel (.xlsx)", type=["xlsx"], key="dbr_up")
            if up and st.button("Process Upload", type="primary", key="dbr_proc"):
                with st.spinner("Parsing..."):
                    batch_id = str(uuid.uuid4())[:8]
                    parsed, errors = parse_dbr_excel(up.read(), up.name)
                    for e in errors: st.warning(e)
                    if parsed:
                        sheets,rows = store_dbr_batch(parsed,up.name,batch_id)
                        st.success(f"Loaded {rows} rows across {sheets} sheets from {up.name}")
                    else: st.error("No sheets loaded — check file format.")
        info = last_upload_info()
        if info: st.caption(f"Last upload: **{info[0]}** — {info[2]} rows, {info[1]} sheets — {info[3][:16]} UTC")
        else: st.caption("No file uploaded yet — showing demo data.")
    sheet_names = list(SHEET_CFG.keys())
    tabs = st.tabs(sheet_names)
    for i,sheet_name in enumerate(sheet_names):
        cfg = SHEET_CFG[sheet_name]
        with tabs[i]:
            df = load_dbr_sheet(sheet_name, carrier_filter=active_scac if active_scac and cfg["carrier_col"] else None)
            if df.empty:
                df = MOCK_DBR.get(sheet_name, pd.DataFrame()).copy()
                if active_scac and cfg["carrier_col"] and cfg["carrier_col"] in df.columns:
                    df = df[df[cfg["carrier_col"]]==active_scac]
                if not df.empty: st.caption("Demo data — upload a DBR file to see live data.")
            if df.empty:
                st.info(f"No data for '{sheet_name}'."); continue
            c1,c2,c3 = st.columns([2,2,1])
            with c1:
                srch = st.text_input("Search",placeholder="Container ID...",key=f"ds_{i}",label_visibility="collapsed")
            with c2:
                if not active_scac and cfg["carrier_col"] and cfg["carrier_col"] in df.columns:
                    opts = ["All"] + sorted(df[cfg["carrier_col"]].dropna().unique().tolist())
                    csel = st.selectbox("Carrier",opts,key=f"dc_{i}",label_visibility="collapsed")
                else:
                    csel = "All"
                    if active_scac: st.caption(f"Carrier: **{active_scac}**")
            with c3: st.metric("Rows", len(df))
            fdf = df.copy()
            if srch:
                ccol = next((c for c in cfg["container_cols"] if c in fdf.columns),None)
                if ccol: fdf = fdf[fdf[ccol].str.contains(srch,case=False,na=False)]
            if csel!="All" and cfg["carrier_col"] and cfg["carrier_col"] in fdf.columns:
                fdf = fdf[fdf[cfg["carrier_col"]]==csel]
            st.dataframe(fdf,use_container_width=True,hide_index=True,height=360)
            buf = BytesIO(); fdf.to_excel(buf,index=False,engine="openpyxl")
            st.download_button(f"Export {sheet_name}",data=buf.getvalue(),
                file_name=f"{sheet_name.replace(' ','_')}_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key=f"de_{i}")

# ── DELIVERY REPORT ────────────────────────────────────────────────────────────
DR_COL_MAP = {"Container Id":"container_id","ASN / Load Number":"asn_load_number",
    "Destination FC":"destination_fc","Actual FC":"actual_fc","Actual Delivery Date":"actual_delivery_dt",
    "Supplier":"supplier","PO Number":"po_number","Part Number":"part_number",
    "PO Line Item Description":"part_description","Quantity":"quantity","Carrier":"carrier","Region":"region"}

def store_delivery_report(df_in):
    conn = get_conn(); c = conn.cursor()
    now = datetime.utcnow().isoformat(); inserted = updated = 0
    for _,row in df_in.iterrows():
        vals = {db_col:str(row.get(xl_col,"")).strip() for xl_col,db_col in DR_COL_MAP.items()}
        vals["uploaded_at"] = now
        try:
            c.execute("INSERT INTO delivery_report (container_id,asn_load_number,destination_fc,actual_fc,actual_delivery_dt,supplier,po_number,part_number,part_description,quantity,carrier,region,uploaded_at) VALUES (:container_id,:asn_load_number,:destination_fc,:actual_fc,:actual_delivery_dt,:supplier,:po_number,:part_number,:part_description,:quantity,:carrier,:region,:uploaded_at)",vals)
            inserted += 1
        except sqlite3.IntegrityError:
            c.execute("UPDATE delivery_report SET destination_fc=:destination_fc,actual_fc=:actual_fc,actual_delivery_dt=:actual_delivery_dt,supplier=:supplier,po_number=:po_number,part_number=:part_number,part_description=:part_description,quantity=:quantity,carrier=:carrier,region=:region,uploaded_at=:uploaded_at WHERE container_id=:container_id AND asn_load_number=:asn_load_number",vals)
            updated += 1
    conn.commit(); conn.close(); return inserted, updated

def load_delivery_report(scac=None):
    conn = get_conn()
    q = "SELECT * FROM delivery_report ORDER BY uploaded_at DESC"; params = ()
    if scac: q = "SELECT * FROM delivery_report WHERE carrier=? ORDER BY uploaded_at DESC"; params = (scac,)
    df = pd.read_sql_query(q,conn,params=params); conn.close()
    return df.drop(columns=["id"],errors="ignore")

def page_delivery_report():
    sidebar_nav()
    role = st.session_state.role; scac = st.session_state.scac
    if role == "internal":
        active_scac = st.session_state.get("view_as_scac")
        is_preview  = active_scac is not None
    else:
        active_scac = scac; is_preview = False
    carrier_options = {u:v for u,v in USERS.items() if v["role"]=="carrier"}
    if role=="carrier":
        carr_badge()
    elif is_preview:
        carrier_name = next((f"{v['display']} ({v['scac']})" for v in carrier_options.values() if v["scac"]==active_scac), active_scac)
        preview_badge(carrier_name)
    else:
        int_badge()
    st.title("Delivery Report")
    if role=="internal" and not is_preview:
        st.caption("Upload delivery data and view all carrier records.")
        with st.expander("Upload Delivery Report", expanded=False):
            up = st.file_uploader("Delivery Report (.xlsx)", type=["xlsx"], key="dr_up")
            if up and st.button("Process Upload", type="primary", key="dr_proc"):
                with st.spinner("Parsing..."):
                    try:
                        df_raw = pd.read_excel(BytesIO(up.read()), dtype=str).fillna("")
                        ins,upd = store_delivery_report(df_raw)
                        st.success(f"Done — {ins} new rows, {upd} updated.")
                    except Exception as e: st.error(f"Error: {e}")
    elif role=="carrier": st.caption(f"Showing records for **{st.session_state.display_name}** ({scac}).")
    else: st.caption(f"Previewing records visible to **{carrier_name}**.")
    df = load_delivery_report(active_scac)
    if df.empty:
        df = MOCK_DELIVERY_DF.copy()
        if active_scac: df = df[df["carrier"]==active_scac]
        if not df.empty and role!="carrier": st.caption("Demo data — upload a Delivery Report to see live records.")
    if df.empty:
        st.info("No records found." + (" Upload a file above." if role=="internal" and not is_preview else "")); return
    c1,c2,c3 = st.columns([2,2,2])
    with c1:
        srch = st.text_input("Search",placeholder="Container ID or ASN...",key="dr_srch",label_visibility="collapsed")
    with c2:
        fcs = ["All FCs"] + sorted(df["destination_fc"].dropna().unique().tolist())
        fc_sel = st.selectbox("FC",fcs,key="dr_fc",label_visibility="collapsed")
    with c3:
        if role=="internal" and not is_preview:
            carr_opts = ["All Carriers"] + sorted(df["carrier"].dropna().unique().tolist())
            carr_sel  = st.selectbox("Carrier",carr_opts,key="dr_carr",label_visibility="collapsed")
        else: carr_sel = "All Carriers"
    fdf = df.copy()
    if srch:
        fdf = fdf[fdf["container_id"].str.contains(srch,case=False,na=False)|fdf["asn_load_number"].str.contains(srch,case=False,na=False)]
    if fc_sel!="All FCs": fdf = fdf[fdf["destination_fc"]==fc_sel]
    if carr_sel!="All Carriers": fdf = fdf[fdf["carrier"]==carr_sel]
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Records",    len(fdf))
    m2.metric("Containers", fdf["container_id"].nunique())
    m3.metric("Dest FCs",   fdf["destination_fc"].nunique())
    m4.metric("Carriers",   fdf["carrier"].nunique())
    tab_tbl,tab_chart = st.tabs(["Data","Charts"])
    with tab_tbl:
        st.dataframe(fdf,use_container_width=True,hide_index=True,height=420)
        buf = BytesIO(); fdf.to_excel(buf,index=False,engine="openpyxl")
        st.download_button("Export to Excel",data=buf.getvalue(),
            file_name=f"delivery_report_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="dr_exp")
    with tab_chart:
        if not fdf.empty:
            col_a,col_b = st.columns(2)
            with col_a:
                fg = fdf.groupby("destination_fc")["quantity"].sum().reset_index()
                fig = px.bar(fg,x="destination_fc",y="quantity",title="Quantity by Dest FC",color_discrete_sequence=["#1E88E5"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
                st.plotly_chart(fig,use_container_width=True)
            with col_b:
                cg = fdf.groupby("carrier")["container_id"].nunique().reset_index(); cg.columns=["Carrier","Containers"]
                fig2 = px.pie(cg,names="Carrier",values="Containers",title="Deliveries by Carrier",hole=0.35,
                              color_discrete_sequence=px.colors.qualitative.Pastel)
                fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",font_color="#ccc")
                st.plotly_chart(fig2,use_container_width=True)

# ── CARRIER PORTAL CONSTANTS ───────────────────────────────────────────────────
SUBMISSION_DEADLINE_HOUR_UTC = 22  # 3 PM MST = 22:00 UTC

CARRIER_CONTAINERS = {
    "ARVY": [
        {"container_id":"MSCU1234567","dest_fc":"RIC6","eta":str(_t+timedelta(1)), "default_status":"Available",            "origin_port":"Norfolk"},
        {"container_id":"CMAU3345678","dest_fc":"RIC6","eta":str(_t+timedelta(2)), "default_status":"OA - Missing Del Appt","origin_port":"Norfolk"},
        {"container_id":"FCIU2345678","dest_fc":"RIC6","eta":str(_t+timedelta(9)), "default_status":"In Transit",           "origin_port":"Norfolk"},
    ],
    "ATMI": [
        {"container_id":"TCKU9871234","dest_fc":"LAX9","eta":str(_t+timedelta(14)),"default_status":"On Water",             "origin_port":"Long Beach"},
        {"container_id":"SUDU8901234","dest_fc":"RIC6","eta":str(_t-timedelta(1)), "default_status":"Demurrage Risk",       "origin_port":"Savannah"},
    ],
    "HRRD": [
        {"container_id":"HLXU8765432","dest_fc":"ILM1","eta":str(_t+timedelta(2)), "default_status":"Delivery Appt Set",   "origin_port":"Wilmington"},
    ],
    "RKNE": [
        {"container_id":"MRKU4456789","dest_fc":"BOS7","eta":str(_t+timedelta(3)), "default_status":"Avail-Pending OA",    "origin_port":"Norfolk"},
        {"container_id":"PONU4567890","dest_fc":"EWR4","eta":str(_t+timedelta(11)),"default_status":"On Water",            "origin_port":"Newark"},
    ],
    "TGHE": [
        {"container_id":"OOLU6789012","dest_fc":"BOS7","eta":str(_t),              "default_status":"Available",           "origin_port":"Savannah"},
    ],
    "GBDV": [
        {"container_id":"GLVU1122334","dest_fc":"BOS7","eta":str(_t+timedelta(12)),"default_status":"On Water",            "origin_port":"Baltimore"},
        {"container_id":"GLVU5566778","dest_fc":"EWR4","eta":str(_t+timedelta(1)), "default_status":"Available",           "origin_port":"Newark"},
    ],
}

BRIDGE_REQUIRED = {"Avail-Pending OA","OA - Missing Del Appt","Demurrage Risk","Available","Pending OA"}

STATUS_OPTIONS = [
    "","Available","Avail-Pending OA","OA - Missing Del Appt",
    "Delivery Appt Set","Completed Pickup","Delivered",
    "On Water","In Transit","Demurrage Risk","Other"
]

def get_deadline_info():
    now = datetime.utcnow()
    deadline = now.replace(hour=SUBMISSION_DEADLINE_HOUR_UTC, minute=0, second=0, microsecond=0)
    if now >= deadline:
        deadline += timedelta(days=1)
    remaining = deadline - now
    h = int(remaining.total_seconds() // 3600)
    m = int((remaining.total_seconds() % 3600) // 60)
    urgent = remaining.total_seconds() <= 7200  # < 2 hrs
    return h, m, urgent

def load_carrier_subs(scac, sub_date):
    conn = get_conn()
    rows = conn.execute(
        "SELECT container_id, current_status, current_bridge, prior_bridge, planned_pu_date, notes, is_submitted FROM carrier_submissions WHERE submission_date=? AND carrier_scac=?",
        (sub_date, scac)
    ).fetchall()
    conn.close()
    return {r[0]: {"status":r[1],"current_bridge":r[2],"prior_bridge":r[3],
                   "planned_pu":r[4],"notes":r[5],"submitted":bool(r[6])} for r in rows}

def upsert_submission(scac, sub_date, cid, status, curr_bridge, prior_bridge, planned_pu, notes, submit):
    conn = get_conn()
    conn.execute("""INSERT OR REPLACE INTO carrier_submissions
        (submission_date,carrier_scac,container_id,current_status,current_bridge,prior_bridge,
         planned_pu_date,notes,is_submitted,submitted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (sub_date, scac, cid, status, curr_bridge, prior_bridge,
         str(planned_pu), notes, 1 if submit else 0,
         datetime.utcnow().isoformat() if submit else None))
    conn.commit(); conn.close()

# ── CARRIER PORTAL ─────────────────────────────────────────────────────────────
def page_carrier_portal():
    sidebar_nav()
    scac = st.session_state.scac
    carr_badge()
    st.title(f"Daily Submission Portal")
    st.caption(f"{st.session_state.display_name} ({scac}) — submit your container updates by the daily deadline.")

    # Deadline banner
    h, m, urgent = get_deadline_info()
    dl_color  = "#c0392b" if urgent else "#e67e22" if h < 3 else "#1a472a"
    dl_label  = "URGENT — DEADLINE APPROACHING" if urgent else f"{h}h {m}m remaining"
    st.markdown(f"""<div style='background:{dl_color};border-radius:8px;padding:12px 20px;
    margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;'>
      <div>
        <span style='color:#fff;font-weight:700;font-size:14px;'>Daily Deadline: 3:00 PM MST</span>
        {"<span style='color:#ffd580;font-size:12px;margin-left:12px;'>⚠ " + dl_label + "</span>" if urgent else ""}
      </div>
      <span style='color:#fff;font-size:20px;font-weight:700;'>{dl_label if not urgent else "Submit now"}</span>
    </div>""", unsafe_allow_html=True)

    tab_sub, tab_hist, tab_dr = st.tabs(["Today's Submission","Submission History","Delivery Report"])

    with tab_sub:
        today_str  = str(_t)
        containers = CARRIER_CONTAINERS.get(scac, [])
        saved      = load_carrier_subs(scac, today_str)
        submitted_set = {cid for cid, d in saved.items() if d["submitted"]}
        n_total    = len(containers)
        n_submitted= len(submitted_set)
        n_needs_bridge = sum(1 for c in containers if c["default_status"] in BRIDGE_REQUIRED and c["container_id"] not in submitted_set)

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Containers Today",  n_total)
        m2.metric("Submitted",         n_submitted, delta=f"{n_total-n_submitted} remaining")
        m3.metric("Need Bridge",       n_needs_bridge)
        m4.metric("Deadline",          "3 PM MST")

        if n_submitted == n_total and n_total > 0:
            st.success(f"All {n_total} containers submitted for today. Thank you!")
        else:
            st.caption("Complete each container below. Containers marked **Bridge Required** need a status explanation before submitting.")

        st.divider()

        for i, cont in enumerate(containers):
            cid     = cont["container_id"]
            saved_c = saved.get(cid, {})
            already = cid in submitted_set
            needs_b = cont["default_status"] in BRIDGE_REQUIRED
            def_st  = saved_c.get("status", cont["default_status"])

            icon  = "✅" if already else ("🔴" if needs_b else "🔵")
            label = f"{icon}  {cid}  |  {cont['dest_fc']}  |  ETA {cont['eta']}  |  {cont['origin_port']}"
            if already: label += "  — Submitted"
            elif needs_b: label += "  — Bridge Required"

            with st.expander(label, expanded=(not already and i == 0)):
                if already:
                    st.success("Submitted for today.")
                    sc1,sc2 = st.columns(2)
                    sc1.markdown(f"**Status:** {saved_c.get('status','—')}")
                    sc2.markdown(f"**Bridge:** {saved_c.get('current_bridge','—') or 'N/A'}")
                    if saved_c.get("notes"): st.markdown(f"**Notes:** {saved_c['notes']}")
                    continue

                cc1,cc2,cc3 = st.columns([2,2,1])
                with cc1:
                    idx = STATUS_OPTIONS.index(def_st) if def_st in STATUS_OPTIONS else 0
                    status = st.selectbox("Status *", STATUS_OPTIONS, index=idx, key=f"st_{scac}_{i}")
                with cc2:
                    try:
                        pu_default = date.fromisoformat(saved_c["planned_pu"]) if saved_c.get("planned_pu") else _t+timedelta(1)
                    except Exception:
                        pu_default = _t+timedelta(1)
                    planned_pu = st.date_input("Planned PU Date", value=pu_default, key=f"pu_{scac}_{i}")
                with cc3:
                    st.metric("Dest FC", cont["dest_fc"])

                show_bridge = needs_b or (status in BRIDGE_REQUIRED)
                if show_bridge:
                    st.markdown("---")
                    st.markdown("**🔴 Bridge Required** — provide full context so the AGL team has a complete picture.")
                    b1,b2 = st.columns(2)
                    with b1:
                        prior_bridge = st.text_input(
                            "Prior Day's Bridge",
                            value=saved_c.get("prior_bridge",""),
                            placeholder="What was yesterday's status/hold?",
                            key=f"prior_{scac}_{i}")
                    with b2:
                        curr_bridge = st.text_input(
                            "Current Bridge *",
                            value=saved_c.get("current_bridge",""),
                            placeholder="What is the current hold or issue?",
                            key=f"curr_{scac}_{i}")
                    notes = st.text_area(
                        "Full Context / Notes *",
                        value=saved_c.get("notes",""),
                        placeholder="Complete background: timeline of events, contacts made with port/FC/driver, expected resolution date, escalation status if applicable...",
                        height=110, key=f"notes_{scac}_{i}")
                    bridge_ok = bool(curr_bridge.strip() and notes.strip())
                    if not bridge_ok:
                        st.warning("Current Bridge and Notes are required before submitting.")
                else:
                    prior_bridge = curr_bridge = ""
                    notes = st.text_input("Notes (optional)", value=saved_c.get("notes",""),
                                          placeholder="Any relevant updates...", key=f"notes_{scac}_{i}")
                    bridge_ok = True

                ba, bb = st.columns([2,1])
                with ba:
                    if st.button(f"Save Draft", key=f"draft_{scac}_{i}", use_container_width=True):
                        upsert_submission(scac, today_str, cid, status, curr_bridge, prior_bridge, planned_pu, notes, False)
                        st.success("Draft saved.")
                with bb:
                    sub_disabled = not bridge_ok
                    if st.button(f"Submit ✓", key=f"sub_{scac}_{i}", type="primary", use_container_width=True, disabled=sub_disabled):
                        upsert_submission(scac, today_str, cid, status, curr_bridge, prior_bridge, planned_pu, notes, True)
                        st.rerun()

        st.divider()
        if n_submitted < n_total:
            if st.button("Submit All Remaining (no bridge required)", key="sub_all", use_container_width=True):
                for cont in containers:
                    cid = cont["container_id"]
                    if cid not in submitted_set and cont["default_status"] not in BRIDGE_REQUIRED:
                        upsert_submission(scac, today_str, cid,
                                          saved.get(cid,{}).get("status", cont["default_status"]),
                                          "","",_t+timedelta(1),"",True)
                st.rerun()

    with tab_hist:
        conn = get_conn()
        hist = pd.read_sql_query(
            "SELECT submission_date, container_id, current_status, current_bridge, notes, is_submitted, submitted_at FROM carrier_submissions WHERE carrier_scac=? ORDER BY submission_date DESC, submitted_at DESC LIMIT 100",
            conn, params=(scac,))
        conn.close()
        if hist.empty:
            hist = pd.DataFrame([
                {"submission_date":str(_t-timedelta(1)),"container_id":"HLXU8765432","current_status":"Delivery Appt Set","current_bridge":"","notes":"Confirmed appt at ILM1 07:30","is_submitted":1,"submitted_at":str(_t-timedelta(1))+" 19:45 UTC"},
                {"submission_date":str(_t-timedelta(2)),"container_id":"HLXU8765432","current_status":"Completed Pickup","current_bridge":"","notes":"Picked up at Wilmington port","is_submitted":1,"submitted_at":str(_t-timedelta(2))+" 20:12 UTC"},
            ])
            st.caption("Demo history — live submissions will appear here.")
        hist["Submitted"] = hist["is_submitted"].map({1:"Yes",0:"Draft"})
        st.dataframe(hist.drop(columns=["is_submitted"],errors="ignore"), use_container_width=True, hide_index=True, height=320)

    with tab_dr:
        df = load_delivery_report(scac)
        if df.empty:
            df = MOCK_DELIVERY_DF[MOCK_DELIVERY_DF["carrier"]==scac].copy()
        st.metric("Delivery Records", len(df))
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True, height=340)
            buf = BytesIO(); df.to_excel(buf, index=False, engine="openpyxl")
            st.download_button("Export", data=buf.getvalue(),
                file_name=f"delivery_report_{scac}_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="cp_dr_exp")
        else:
            st.info("No delivery records on file.")



# ── ROUTER ─────────────────────────────────────────────────────────────────────
if not st.session_state.auth:
    page_login()
else:
    pg = st.session_state.page
    if   pg == "landing":         page_landing()
    elif pg == "shipments":       page_shipments()
    elif pg == "track":           page_track()
    elif pg == "quote":           page_quote()
    elif pg == "dashboard":       page_dashboard()
    elif pg == "dbr_dashboard":   page_dbr_dashboard()
    elif pg == "delivery_report": page_delivery_report()
    elif pg == "carrier_portal":   page_carrier_portal()
    else:                         page_landing()
