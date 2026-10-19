# Project Continuum - Amazon Global Logistics Digital Platform
# v2.0 - DBR Dashboard + Delivery Report automation

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import json
import os
import uuid
from datetime import datetime, date
from io import BytesIO

# ── PAGE CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Continuum | Amazon Global Logistics",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CREDENTIALS ────────────────────────────────────────────────────────────────
USERS = {
    "agladmin": {"password": "continuum2026", "role": "internal", "scac": None,   "display": "AGL Admin"},
    "arvy": {"password": "arvy2026",      "role": "carrier",  "scac": "ARVY", "display": "Arrive Logistics"},
    "atmi": {"password": "atmi2026",      "role": "carrier",  "scac": "ATMI", "display": "ATM Inc."},
    "hudd": {"password": "hudd2026",      "role": "carrier",  "scac": "HUDD", "display": "Huddle Transport"},
    "rkne": {"password": "rkne2026",      "role": "carrier",  "scac": "RKNE", "display": "Roekcne"},
    "tghe": {"password": "tghe2026",      "role": "carrier",  "scac": "TGHE", "display": "TGH Express"},
}

# ── DB PATH ────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuum.db")

# ── SHEET CONFIG ───────────────────────────────────────────────────────────────
SHEET_CFG = {
    "Avail-Pending OA": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": "Carrier",
    },
    "OA - Missing Del Appt": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": "Carrier",
    },
    "Completed Pickups": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": "Carrier",
    },
    "Delivery Appointments": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": "Carrier",
    },
    "Completed Deliveries": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": None,
    },
    "Delivery Plan": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": None,
    },
    "On Water": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": None,
    },
    "Demurrage": {
        "container_cols": ["Container", "Container ID", "Loaded Container", "Container #"],
        "carrier_col": "Carrier",
    },
}

# ── SESSION STATE ──────────────────────────────────────────────────────────────
DEFAULTS = {
    "auth": False,
    "page": "landing",
    "role": "external",
    "scac": None,
    "username": None,
    "display_name": "Guest",
    "track_query": "",
    "quote_done": False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


def nav(page):
    st.session_state.page = page
    st.rerun()


# ── DATABASE ───────────────────────────────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dbr_containers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_name TEXT,
            container_id TEXT,
            carrier TEXT,
            status_label TEXT,
            row_data TEXT,
            upload_batch TEXT,
            uploaded_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS delivery_report (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_id TEXT,
            asn_load_number TEXT,
            destination_fc TEXT,
            actual_fc TEXT,
            actual_delivery_dt TEXT,
            supplier TEXT,
            po_number TEXT,
            part_number TEXT,
            part_description TEXT,
            quantity REAL,
            carrier TEXT,
            region TEXT,
            uploaded_at TEXT,
            UNIQUE(container_id, asn_load_number)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS dbr_upload_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            file_name TEXT,
            sheets_loaded INTEGER,
            rows_loaded INTEGER,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()

# ── GLOBAL CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
#MainMenu{visibility:hidden;}footer{visibility:hidden;}header{visibility:hidden;}
.block-container{padding-top:1.2rem!important;}
.stButton>button{border-radius:4px;font-weight:600;}
.internal-banner{background:#1a472a;color:#fff;padding:6px 16px;border-radius:4px;
  font-size:13px;margin-bottom:12px;display:inline-block;}
.carrier-banner{background:#1a3a5c;color:#fff;padding:6px 16px;border-radius:4px;
  font-size:13px;margin-bottom:12px;display:inline-block;}
</style>
""", unsafe_allow_html=True)


# ── SHARED UI ──────────────────────────────────────────────────────────────────
def internal_banner():
    st.markdown('<div class="internal-banner">&#x1F512; Internal View — AGL Team</div>', unsafe_allow_html=True)


def carrier_banner():
    name = st.session_state.display_name
    scac = st.session_state.scac
    st.markdown(f'<div class="carrier-banner">&#x1F69B; {name} ({scac}) — Carrier Portal</div>', unsafe_allow_html=True)


def sidebar_nav():
    role = st.session_state.role
    with st.sidebar:
        st.markdown(f"**{st.session_state.display_name}**")
        st.markdown("---")
        nav_items = [
            ("Home", "landing"),
            ("Shipments", "shipments"),
            ("Track & Trace", "track"),
            ("Get a Quote", "quote"),
        ]
        if role == "internal":
            nav_items += [
                ("Internal Dashboard", "dashboard"),
                ("DBR Dashboard", "dbr_dashboard"),
                ("Delivery Report", "delivery_report"),
            ]
        else:
            nav_items += [("Delivery Report", "delivery_report")]
        for label, pg in nav_items:
            if st.button(label, key=f"snav_{pg}", use_container_width=True):
                nav(pg)
        st.markdown("---")
        if st.button("Sign Out", key="signout", use_container_width=True):
            for k in list(DEFAULTS.keys()):
                st.session_state[k] = DEFAULTS[k]
            st.rerun()


# ── LOGIN ──────────────────────────────────────────────────────────────────────
def page_login():
    st.markdown("""
    <style>
    .block-container{padding:0!important;max-width:100%!important;}
    </style>
    <div style='background:#0B1623;min-height:100vh;display:flex;flex-direction:column;
    align-items:center;justify-content:center;padding:40px;font-family:Segoe UI,sans-serif;'>
      <div style='max-width:460px;width:100%;'>
        <div style='text-align:center;margin-bottom:40px;'>
          <div style='font-size:52px;margin-bottom:12px;'>&#x1F310;</div>
          <h1 style='color:#fff;font-size:34px;font-weight:700;margin:0;letter-spacing:-0.5px;'>Continuum</h1>
          <p style='color:#8899AA;font-size:15px;margin-top:8px;'>Amazon Global Logistics</p>
        </div>
        <div style='background:#132133;border:1px solid #1E3A52;border-radius:12px;padding:32px;'>
          <p style='color:#ccc;font-size:14px;margin-bottom:20px;'>Sign in to continue.</p>
    """, unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Username", key="li_user")
    password = st.text_input("Password", type="password", placeholder="Password", key="li_pass")
    btn = st.button("Sign In", use_container_width=True, type="primary", key="li_btn")

    if btn:
        u = username.strip().lower()
        if u in USERS and USERS[u]["password"] == password:
            st.session_state.auth = True
            st.session_state.username = u
            st.session_state.role = USERS[u]["role"]
            st.session_state.scac = USERS[u]["scac"]
            st.session_state.display_name = USERS[u]["display"]
            st.session_state.page = "delivery_report" if USERS[u]["role"] == "carrier" else "landing"
            st.rerun()
        else:
            st.error("Invalid credentials.")

    st.markdown("</div></div></div>", unsafe_allow_html=True)


# ── DBR DASHBOARD (internal only) ─────────────────────────────────────────────
def parse_dbr_excel(file_bytes, file_name):
    results = {}
    errors = []
    try:
        xl = pd.ExcelFile(BytesIO(file_bytes))
    except Exception as e:
        return {}, [f"Cannot open file: {e}"]
    for sheet, cfg in SHEET_CFG.items():
        if sheet not in xl.sheet_names:
            errors.append(f"Sheet '{sheet}' not found — skipped.")
            continue
        try:
            df = pd.read_excel(xl, sheet_name=sheet, dtype=str).fillna("")
            container_col = next((c for c in cfg["container_cols"] if c in df.columns), None)
            rows = []
            for _, row in df.iterrows():
                rd = row.to_dict()
                cid = str(rd.get(container_col, "")).strip() if container_col else ""
                carrier = str(rd.get(cfg["carrier_col"], "")).strip() if cfg["carrier_col"] else ""
                rows.append({"container_id": cid, "carrier": carrier, "row_data": rd})
            results[sheet] = rows
        except Exception as e:
            errors.append(f"Sheet '{sheet}' error: {e}")
    return results, errors


def store_dbr_batch(parsed, file_name, batch_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM dbr_containers")
    now = datetime.utcnow().isoformat()
    total_rows = 0
    sheets_loaded = 0
    for sheet_name, rows in parsed.items():
        for row in rows:
            c.execute(
                "INSERT INTO dbr_containers (sheet_name,container_id,carrier,status_label,row_data,upload_batch,uploaded_at) VALUES (?,?,?,?,?,?,?)",
                (sheet_name, row["container_id"], row["carrier"], sheet_name, json.dumps(row["row_data"]), batch_id, now),
            )
        total_rows += len(rows)
        sheets_loaded += 1
    c.execute(
        "INSERT INTO dbr_upload_log (batch_id,file_name,sheets_loaded,rows_loaded,uploaded_at) VALUES (?,?,?,?,?)",
        (batch_id, file_name, sheets_loaded, total_rows, now),
    )
    conn.commit()
    conn.close()
    return sheets_loaded, total_rows


def load_dbr_sheet(sheet_name, carrier_filter=None):
    conn = get_conn()
    if carrier_filter:
        rows = conn.execute(
            "SELECT row_data FROM dbr_containers WHERE sheet_name=? AND carrier=?",
            (sheet_name, carrier_filter),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT row_data FROM dbr_containers WHERE sheet_name=?",
            (sheet_name,),
        ).fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([json.loads(r[0]) for r in rows])


def last_upload_info():
    conn = get_conn()
    row = conn.execute(
        "SELECT file_name, sheets_loaded, rows_loaded, uploaded_at FROM dbr_upload_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def page_dbr_dashboard():
    if st.session_state.role != "internal":
        st.error("Access denied.")
        return
    sidebar_nav()

    # ── View-as selector ──────────────────────────────────────────────────────
    carrier_options = {u: v for u, v in USERS.items() if v["role"] == "carrier"}
    view_labels = ["Internal (All Carriers)"] + [f"{v['display']} ({v['scac']})" for v in carrier_options.values()]
    view_scacs  = [None] + [v["scac"] for v in carrier_options.values()]

    view_col, _ = st.columns([3, 5])
    with view_col:
        view_idx = st.selectbox(
            "Viewing as",
            range(len(view_labels)),
            format_func=lambda i: view_labels[i],
            key="dbr_view_as",
            label_visibility="collapsed",
        )
    active_scac = view_scacs[view_idx]

    if active_scac:
        display = view_labels[view_idx]
        st.markdown(f'<div class="carrier-banner">&#x1F441; Previewing carrier view: <strong>{display}</strong></div>', unsafe_allow_html=True)
    else:
        internal_banner()

    st.title("DBR Dashboard")
    st.caption("Daily Booking Report — container tracking across all carriers and statuses.")

    # Upload only visible in internal view
    if not active_scac:
        with st.expander("Upload DBR File", expanded=False):
            up = st.file_uploader("DBR Excel (.xlsx)", type=["xlsx"], key="dbr_up")
            if up and st.button("Process Upload", type="primary", key="dbr_proc"):
                with st.spinner("Parsing..."):
                    batch_id = str(uuid.uuid4())[:8]
                    parsed, errors = parse_dbr_excel(up.read(), up.name)
                    for e in errors:
                        st.warning(e)
                    if parsed:
                        sheets, rows = store_dbr_batch(parsed, up.name, batch_id)
                        st.success(f"Loaded {rows} rows across {sheets} sheets from {up.name}")
                    else:
                        st.error("No sheets loaded — check file format.")

        info = last_upload_info()
        if info:
            st.caption(f"Last upload: **{info[0]}** — {info[2]} rows, {info[1]} sheets — {info[3][:16]} UTC")

    sheet_names = list(SHEET_CFG.keys())
    tabs = st.tabs(sheet_names)
    for i, sheet_name in enumerate(sheet_names):
        cfg = SHEET_CFG[sheet_name]
        with tabs[i]:
            # Carrier preview: pre-filter by SCAC; otherwise load all
            df = load_dbr_sheet(sheet_name, carrier_filter=active_scac if active_scac and cfg["carrier_col"] else None)
            if df.empty:
                if active_scac:
                    st.info(f"No data for {active_scac} in '{sheet_name}'.")
                else:
                    st.info(f"No data for '{sheet_name}'. Upload a DBR file above.")
                continue
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                srch = st.text_input("Search", placeholder="Container ID...", key=f"ds_{i}", label_visibility="collapsed")
            with c2:
                # In carrier preview, carrier filter is locked; in internal view show dropdown
                if not active_scac and cfg["carrier_col"] and cfg["carrier_col"] in df.columns:
                    opts = ["All"] + sorted(df[cfg["carrier_col"]].dropna().unique().tolist())
                    csel = st.selectbox("Carrier", opts, key=f"dc_{i}", label_visibility="collapsed")
                else:
                    csel = "All"
                    if active_scac:
                        st.caption(f"Carrier: **{active_scac}**")
            with c3:
                st.metric("Rows", len(df))
            fdf = df.copy()
            if srch:
                ccol = next((c for c in cfg["container_cols"] if c in fdf.columns), None)
                if ccol:
                    fdf = fdf[fdf[ccol].str.contains(srch, case=False, na=False)]
            if csel != "All" and cfg["carrier_col"] and cfg["carrier_col"] in fdf.columns:
                fdf = fdf[fdf[cfg["carrier_col"]] == csel]
            st.dataframe(fdf, use_container_width=True, height=420)
            buf = BytesIO()
            fdf.to_excel(buf, index=False, engine="openpyxl")
            st.download_button(
                f"Export {sheet_name}",
                data=buf.getvalue(),
                file_name=f"{sheet_name.replace(' ','_')}_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"de_{i}",
            )


# ── DELIVERY REPORT ────────────────────────────────────────────────────────────
DR_COL_MAP = {
    "Container Id":             "container_id",
    "ASN / Load Number":        "asn_load_number",
    "Destination FC":           "destination_fc",
    "Actual FC":                "actual_fc",
    "Actual Delivery Date":     "actual_delivery_dt",
    "Supplier":                 "supplier",
    "PO Number":                "po_number",
    "Part Number":              "part_number",
    "PO Line Item Description": "part_description",
    "Quantity":                 "quantity",
    "Carrier":                  "carrier",
    "Region":                   "region",
}


def store_delivery_report(df_in):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    inserted = updated = 0
    for _, row in df_in.iterrows():
        vals = {db_col: str(row.get(xl_col, "")).strip() for xl_col, db_col in DR_COL_MAP.items()}
        vals["uploaded_at"] = now
        try:
            c.execute(
                "INSERT INTO delivery_report (container_id,asn_load_number,destination_fc,actual_fc,actual_delivery_dt,supplier,po_number,part_number,part_description,quantity,carrier,region,uploaded_at) VALUES (:container_id,:asn_load_number,:destination_fc,:actual_fc,:actual_delivery_dt,:supplier,:po_number,:part_number,:part_description,:quantity,:carrier,:region,:uploaded_at)",
                vals,
            )
            inserted += 1
        except sqlite3.IntegrityError:
            c.execute(
                "UPDATE delivery_report SET destination_fc=:destination_fc,actual_fc=:actual_fc,actual_delivery_dt=:actual_delivery_dt,supplier=:supplier,po_number=:po_number,part_number=:part_number,part_description=:part_description,quantity=:quantity,carrier=:carrier,region=:region,uploaded_at=:uploaded_at WHERE container_id=:container_id AND asn_load_number=:asn_load_number",
                vals,
            )
            updated += 1
    conn.commit()
    conn.close()
    return inserted, updated


def load_delivery_report(scac=None):
    conn = get_conn()
    q = "SELECT * FROM delivery_report ORDER BY uploaded_at DESC"
    params = ()
    if scac:
        q = "SELECT * FROM delivery_report WHERE carrier=? ORDER BY uploaded_at DESC"
        params = (scac,)
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    return df.drop(columns=["id"], errors="ignore")


def page_delivery_report():
    sidebar_nav()
    role = st.session_state.role
    scac = st.session_state.scac

    # ── View-as selector (internal only) ─────────────────────────────────────
    if role == "internal":
        carrier_options = {u: v for u, v in USERS.items() if v["role"] == "carrier"}
        view_labels = ["Internal (All Carriers)"] + [f"{v['display']} ({v['scac']})" for v in carrier_options.values()]
        view_scacs  = [None] + [v["scac"] for v in carrier_options.values()]
        view_col, _ = st.columns([3, 5])
        with view_col:
            view_idx = st.selectbox(
                "Viewing as",
                range(len(view_labels)),
                format_func=lambda i: view_labels[i],
                key="dr_view_as",
                label_visibility="collapsed",
            )
        active_scac = view_scacs[view_idx]
        is_carrier_preview = active_scac is not None
    else:
        active_scac = scac
        is_carrier_preview = False

    # ── Banner ────────────────────────────────────────────────────────────────
    if role == "carrier":
        carrier_banner()
    elif is_carrier_preview:
        display = view_labels[view_idx]
        st.markdown(f'<div class="carrier-banner">&#x1F441; Previewing carrier view: <strong>{display}</strong></div>', unsafe_allow_html=True)
    else:
        internal_banner()

    st.title("Delivery Report")

    # ── Upload (internal full-view only) ──────────────────────────────────────
    if role == "internal" and not is_carrier_preview:
        st.caption("Upload delivery data and view all carrier records.")
        with st.expander("Upload Delivery Report", expanded=False):
            up = st.file_uploader("Delivery Report (.xlsx)", type=["xlsx"], key="dr_up")
            if up and st.button("Process Upload", type="primary", key="dr_proc"):
                with st.spinner("Parsing..."):
                    try:
                        df_raw = pd.read_excel(BytesIO(up.read()), dtype=str).fillna("")
                        ins, upd = store_delivery_report(df_raw)
                        st.success(f"Done — {ins} new rows, {upd} updated.")
                    except Exception as e:
                        st.error(f"Error: {e}")
    elif role == "carrier":
        st.caption(f"Showing delivery records for **{st.session_state.display_name}** ({scac}).")
    else:
        st.caption(f"Previewing records visible to **{view_labels[view_idx]}**.")

    # ── Load data ─────────────────────────────────────────────────────────────
    df = load_delivery_report(active_scac)
    if df.empty:
        msg = "No records found."
        if role == "internal" and not is_carrier_preview:
            msg += " Upload a file above."
        st.info(msg)
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        srch = st.text_input("Search", placeholder="Container ID or ASN...", key="dr_srch", label_visibility="collapsed")
    with c2:
        fcs = ["All"] + sorted(df["destination_fc"].dropna().unique().tolist())
        fc_sel = st.selectbox("FC", fcs, key="dr_fc", label_visibility="collapsed")
    with c3:
        # In full internal view only, allow further carrier filter
        if role == "internal" and not is_carrier_preview:
            carr_opts = ["All"] + sorted(df["carrier"].dropna().unique().tolist())
            carr_sel = st.selectbox("Carrier", carr_opts, key="dr_carr", label_visibility="collapsed")
        else:
            carr_sel = "All"

    fdf = df.copy()
    if srch:
        fdf = fdf[
            fdf["container_id"].str.contains(srch, case=False, na=False) |
            fdf["asn_load_number"].str.contains(srch, case=False, na=False)
        ]
    if fc_sel != "All":
        fdf = fdf[fdf["destination_fc"] == fc_sel]
    if carr_sel != "All":
        fdf = fdf[fdf["carrier"] == carr_sel]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Records", len(fdf))
    m2.metric("Containers", fdf["container_id"].nunique())
    m3.metric("Dest FCs", fdf["destination_fc"].nunique())
    m4.metric("Carriers", fdf["carrier"].nunique())

    st.dataframe(fdf, use_container_width=True, height=460)

    buf = BytesIO()
    fdf.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "Export to Excel",
        data=buf.getvalue(),
        file_name=f"delivery_report_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dr_exp",
    )


# ── LANDING PAGE ───────────────────────────────────────────────────────────────
def page_landing():
    sidebar_nav()
    if st.session_state.role == "internal":
        internal_banner()

    st.markdown("""
    <div style='background:linear-gradient(135deg,#0B1623 0%,#0D2137 100%);
    border-radius:16px;padding:60px 40px;margin-bottom:32px;text-align:center;'>
      <h1 style='color:#fff;font-size:42px;font-weight:700;margin:0;'>
        Amazon Global Logistics
      </h1>
      <p style='color:#8899AA;font-size:18px;margin-top:12px;max-width:600px;margin-left:auto;margin-right:auto;'>
        Connecting global supply chains with precision, speed, and visibility.
      </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    tiles = [
        ("Track & Trace", "Real-time container visibility.", "track"),
        ("Get a Quote", "Instant ocean freight pricing.", "quote"),
        ("Shipments", "Manage active shipments.", "shipments"),
        ("Dashboard", "Internal operations view.", "dashboard"),
    ]
    for col, (title, desc, pg) in zip([c1, c2, c3, c4], tiles):
        with col:
            st.markdown(f"""
            <div style='background:#132133;border:1px solid #1E3A52;border-radius:12px;
            padding:24px;text-align:center;height:140px;'>
              <h4 style='color:#fff;margin:0 0 8px;'>{title}</h4>
              <p style='color:#8899AA;font-size:13px;margin:0;'>{desc}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Open", key=f"tile_{pg}", use_container_width=True):
                nav(pg)

    if st.session_state.role == "internal":
        st.markdown("### Quick Links")
        q1, q2 = st.columns(2)
        with q1:
            if st.button("DBR Dashboard", use_container_width=True, key="ql_dbr"):
                nav("dbr_dashboard")
        with q2:
            if st.button("Delivery Report", use_container_width=True, key="ql_dr"):
                nav("delivery_report")


# ── SHIPMENTS PAGE ─────────────────────────────────────────────────────────────
def page_shipments():
    sidebar_nav()
    if st.session_state.role == "internal":
        internal_banner()
    st.title("Shipments")
    st.caption("Active shipment management — booking, documentation, and status tracking.")
    st.info("Shipments module coming soon.")


# ── TRACK & TRACE ──────────────────────────────────────────────────────────────
def page_track():
    sidebar_nav()
    st.title("Track & Trace")
    st.caption("Enter a container number, B/L, or booking reference to check status.")

    query = st.text_input("Container / B/L / Booking", value=st.session_state.track_query,
                          placeholder="e.g. MSCU1234567", key="track_inp")
    if st.button("Track", type="primary", key="track_btn"):
        st.session_state.track_query = query
        if query.strip():
            st.markdown("---")
            st.markdown(f"**Tracking: {query.strip()}**")
            cols = st.columns(4)
            stages = [("Origin Gate-In", "Completed"), ("On Vessel", "Completed"),
                      ("Discharged", "In Progress"), ("Delivered", "Pending")]
            for col, (stage, status) in zip(cols, stages):
                color = "#1a472a" if status == "Completed" else "#1a3a5c" if status == "In Progress" else "#2a2a2a"
                col.markdown(f"""
                <div style='background:{color};border-radius:8px;padding:16px;text-align:center;'>
                  <div style='color:#fff;font-weight:700;font-size:14px;'>{stage}</div>
                  <div style='color:#aaa;font-size:12px;margin-top:4px;'>{status}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("Enter a container number to track.")


# ── GET A QUOTE ────────────────────────────────────────────────────────────────
def page_quote():
    sidebar_nav()
    st.title("Get a Quote")
    st.caption("Request ocean freight pricing for your shipment.")

    if st.session_state.quote_done:
        st.success("Quote request submitted. Our team will follow up within 24 hours.")
        if st.button("Submit Another", key="quote_reset"):
            st.session_state.quote_done = False
            st.rerun()
        return

    with st.form("quote_form"):
        c1, c2 = st.columns(2)
        with c1:
            origin = st.text_input("Origin Port")
            dest = st.text_input("Destination FC")
            ctype = st.selectbox("Container Type", ["40HC", "45HC", "20GP", "40GP"])
        with c2:
            volume = st.number_input("Volume (TEUs)", min_value=1, value=1)
            commodity = st.text_input("Commodity")
            ready_date = st.date_input("Cargo Ready Date")
        notes = st.text_area("Additional Notes", height=80)
        submitted = st.form_submit_button("Submit Quote Request", type="primary")
        if submitted:
            if origin and dest:
                st.session_state.quote_done = True
                st.rerun()
            else:
                st.error("Origin and Destination are required.")


# ── INTERNAL DASHBOARD ─────────────────────────────────────────────────────────
def page_dashboard():
    if st.session_state.role != "internal":
        st.error("Access denied.")
        return
    internal_banner()
    sidebar_nav()
    st.title("Internal Dashboard")
    st.caption("Operational overview for the AGL team.")

    tab1, tab2, tab3 = st.tabs(["Overview", "Reports", "Settings"])

    with tab1:
        m1, m2, m3, m4 = st.columns(4)
        conn = get_conn()
        dbr_count = conn.execute("SELECT COUNT(*) FROM dbr_containers").fetchone()[0]
        dr_count = conn.execute("SELECT COUNT(*) FROM delivery_report").fetchone()[0]
        last_batch = conn.execute("SELECT file_name FROM dbr_upload_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        m1.metric("DBR Containers", dbr_count)
        m2.metric("Delivery Records", dr_count)
        m3.metric("Active Carriers", len(USERS) - 1)
        m4.metric("Last DBR Upload", last_batch[0][:20] if last_batch else "None")
        st.markdown("---")
        st.markdown("### Carrier Overview")
        conn = get_conn()
        df_carr = pd.read_sql_query(
            "SELECT carrier, COUNT(*) as containers FROM dbr_containers WHERE carrier != '' GROUP BY carrier ORDER BY containers DESC",
            conn
        )
        conn.close()
        if not df_carr.empty:
            fig = px.bar(df_carr, x="carrier", y="containers", title="Containers by Carrier",
                         color_discrete_sequence=["#1E88E5"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#fff", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No carrier data yet. Upload a DBR file.")

    with tab2:
        st.markdown("### Reports")
        r1, r2 = st.columns(2)
        with r1:
            st.markdown("**DBR Dashboard**")
            st.caption("Daily Booking Report — all sheets and carrier views.")
            if st.button("Open DBR Dashboard", key="dash_dbr", use_container_width=True):
                nav("dbr_dashboard")
        with r2:
            st.markdown("**Delivery Report**")
            st.caption("Delivery actuals by container, FC, and carrier.")
            if st.button("Open Delivery Report", key="dash_dr", use_container_width=True):
                nav("delivery_report")

    with tab3:
        st.markdown("### Settings")
        st.info("Configuration options coming soon.")


# ── ROUTER ─────────────────────────────────────────────────────────────────────
if not st.session_state.auth:
    page_login()
else:
    pg = st.session_state.page
    if pg == "landing":
        page_landing()
    elif pg == "shipments":
        page_shipments()
    elif pg == "track":
        page_track()
    elif pg == "quote":
        page_quote()
    elif pg == "dashboard":
        page_dashboard()
    elif pg == "dbr_dashboard":
        page_dbr_dashboard()
    elif pg == "delivery_report":
        page_delivery_report()
    else:
        page_landing()
