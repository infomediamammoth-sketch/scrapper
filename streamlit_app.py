import streamlit as st
import pandas as pd
import io
import os
import re
import datetime
import time
import zipfile
import queue
from concurrent.futures import ThreadPoolExecutor
from scraper import scrape_google_maps

# Auto-install Playwright Chromium once on cloud platforms (Linux)
@st.cache_resource
def init_cloud_browser():
    if os.name != 'nt':
        os.system("playwright install chromium")
    return True

init_cloud_browser()

# Set page config
st.set_page_config(
    page_title="Google Business Listing Scraper",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
HISTORY_DIR = "saved_leads"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# Helper to sanitize sheet names for Excel (max 31 chars, no invalid chars)
def clean_sheet_name(name, existing_names):
    cleaned = re.sub(r'[\\/*?:\[\]]', '', name).strip()
    if not cleaned:
        cleaned = "Sheet"
    cleaned = cleaned[:28]
    candidate = cleaned
    counter = 1
    while candidate.lower() in [e.lower() for e in existing_names]:
        candidate = f"{cleaned[:24]}_{counter}"
        counter += 1
    return candidate

# Helper to retrieve saved runs
def get_history():
    if not os.path.exists(HISTORY_DIR):
        return []
    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".xlsx") and f.startswith("leads_")]
    files.sort(reverse=True)
    
    history_list = []
    for file in files:
        match = re.search(r"leads_(\d{8}_\d{6})_Q-(.*)_L-(.*)_R-(\d+)\.xlsx", file)
        if match:
            ts_raw = match.group(1)
            q_raw = match.group(2).replace("-", " ").title()
            loc_raw = match.group(3).replace("-", " ").title()
            recs = match.group(4)
            
            date_p, time_p = ts_raw.split("_")
            formatted_ts = f"{date_p[0:4]}-{date_p[4:6]}-{date_p[6:8]} {time_p[0:2]}:{time_p[2:4]}:{time_p[4:6]}"
            
            history_list.append({
                "filename": file,
                "timestamp": formatted_ts,
                "query": q_raw,
                "location": loc_raw,
                "records": int(recs)
            })
    return history_list

# CSS for clean, light theme matching previous interface
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    html, body, .stApp, p, span, div, label, input, button, select, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    .stApp {
        background-color: #FFFFFF !important;
    }
    
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
        width: 350px !important;
    }
    
    section[data-testid="stSidebar"] h2 {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        color: #1E293B !important;
        margin-bottom: 0.6rem !important;
    }
    
    section[data-testid="stSidebar"] label p {
        font-weight: 600 !important;
        color: #475569 !important;
        font-size: 0.85rem !important;
    }
    
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primary"]:focus,
    button[data-testid="stBaseButton-primary"]:active {
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        border: none !important;
        border-radius: 6px !important;
        width: 100% !important;
        height: 44px !important;
        transition: all 0.2s ease !important;
    }
    button[data-testid="stBaseButton-primary"]:hover {
        background-color: #1D4ED8 !important;
    }
    
    .download-btn button {
        background-color: #059669 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        width: 100% !important;
        height: 44px !important;
        transition: all 0.2s ease !important;
    }
    .download-btn button:hover {
        background-color: #047857 !important;
        color: #FFFFFF !important;
    }
    
    .block-container {
        max-width: 1200px !important;
        padding-top: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
    }
    
    .worker-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 6px;
        font-size: 0.82rem;
        color: #1E293B;
    }
    </style>
""", unsafe_allow_html=True)

# SIDEBAR: Configuration Area
with st.sidebar:
    st.markdown("## Search Target")
    
    # Entity / Query Mode
    query_mode = st.radio("Search Term Mode", ["Single Query", "Multiple Queries (Queue)"], horizontal=True)
    if query_mode == "Single Query":
        query_input = st.text_input("What to search for?", value="Event Planners", placeholder="e.g. Dentists, Event planners")
        queries_list = [query_input.strip()] if query_input.strip() else []
    else:
        queries_raw = st.text_area(
            "Keywords / Entities (one per line):",
            value="Event Planners\nDentists\nGyms",
            height=90,
            help="Enter each business category or search keyword on a new line."
        )
        raw_q_split = re.split(r'[\n,]+', queries_raw)
        queries_list = [q.strip() for q in raw_q_split if q.strip()]
        if queries_list:
            st.caption(f"🎯 **{len(queries_list)} search term(s)**")

    st.markdown("---")
    st.markdown("## Location Target")
    
    # Location Mode
    loc_mode = st.radio("Location Mode", ["Single Location", "Multiple Locations (Queue)"], horizontal=True)
    if loc_mode == "Single Location":
        location_input = st.text_input("From where to search?", value="Surat, Gujarat", placeholder="e.g. Surat, Gujarat")
        locations_list = [location_input.strip()] if location_input.strip() else []
    else:
        locations_raw = st.text_area(
            "Locations Queue (one per line):",
            value="Surat, Gujarat\nBardoli, Gujarat\nNavsari, Gujarat",
            height=90,
            help="Enter each city or area on a new line or separated by commas."
        )
        raw_loc_split = re.split(r'[\n,]+', locations_raw)
        locations_list = [loc.strip() for loc in raw_loc_split if loc.strip()]
        if locations_list:
            st.caption(f"📍 **{len(locations_list)} location(s)**")
    
    st.markdown("---")
    st.markdown("## Speed & Concurrency")
    
    # Task calculation
    total_planned_tasks = len(queries_list) * len(locations_list)
    suggested_workers = min(max(total_planned_tasks, 1), 4)
    
    parallel_workers = st.slider(
        "Parallel Sessions (Workers)",
        min_value=1,
        max_value=10,
        value=suggested_workers,
        step=1,
        help="Run up to 10 browser sessions at the exact same time. 3 to 5 workers is the recommended sweet spot for maximum speed."
    )
    
    lead_limit = st.slider("Max Results per Search", min_value=10, max_value=1000, value=200, step=10)
    
    if total_planned_tasks > 1:
        st.info(f"⚡ **{total_planned_tasks} tasks queued** running across **{parallel_workers} parallel session(s)**. Estimated ~{parallel_workers}x faster extraction!")
    
    st.markdown("---")
    st.markdown("## Lead Filtering")
    require_phone = st.checkbox(
        "Skip companies without mobile number", 
        value=False, 
        help="When enabled, any business that does not have a phone or mobile number listed on Google Maps will be automatically skipped."
    )
    
    st.markdown("---")
    st.markdown("## Debugging Options")
    headful = st.checkbox("Show Browser (Headful)", value=False, help="Visible browser mode. Keep unchecked when using parallel workers for best performance.")
    
    st.markdown("---")
    st.info("Note: Permanently closed listings are filtered out automatically.")
    
    # Start Button
    start_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# MAIN AREA: Headers
st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 0.5rem;">
        <h1 style="font-size: 2.2rem; font-weight: 800; color: #0F172A; margin: 0;">🔍 Google Business Listing Scraper</h1>
    </div>
    <p style="font-size: 1.05rem; color: #475569; margin-bottom: 1.5rem;">Extract lead lists concurrently from Google Maps business profiles with multi-session parallel workers.</p>
""", unsafe_allow_html=True)

# Session state initialization
if "current_status" not in st.session_state:
    st.session_state.current_status = "idle"
if "current_message" not in st.session_state:
    st.session_state.current_message = "Ready to scrape leads. Configure your targets in the sidebar and click 'Start Scraping'."
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = []
if "results_by_task" not in st.session_state:
    st.session_state.results_by_task = {}
if "task_list" not in st.session_state:
    st.session_state.task_list = []

# Status Display
status_container = st.empty()

def update_status(status, message):
    if status == "running":
        status_container.info(f"⏳ **Active Scraping**: {message}")
    elif status == "completed":
        status_container.success(f"✅ **Success**: {message}")
    elif status == "failed":
        status_container.error(f"❌ **Error**: {message}")
    else:
        status_container.markdown(f"<p style='color: #64748B;'>{message}</p>", unsafe_allow_html=True)

update_status(st.session_state.current_status, st.session_state.current_message)

# Worker runner for thread pool
def execute_worker_task(task_id, q_text, loc_text, limit, is_headful, req_phone, out_q):
    out_q.put({"type": "task_start", "task_id": task_id, "query": q_text, "location": loc_text})
    task_leads = []
    try:
        for event in scrape_google_maps(q_text, loc_text, limit, is_headful, require_phone=req_phone):
            event["task_id"] = task_id
            event["query"] = q_text
            event["location"] = loc_text
            if event["type"] == "data":
                lead_record = dict(event["data"])
                lead_record["Search Query"] = q_text
                lead_record["Searched Location"] = loc_text
                event["data"] = lead_record
                task_leads.append(lead_record)
            out_q.put(event)
        out_q.put({"type": "task_done", "task_id": task_id, "query": q_text, "location": loc_text, "leads": task_leads})
    except Exception as err:
        out_q.put({"type": "task_error", "task_id": task_id, "query": q_text, "location": loc_text, "message": str(err), "leads": task_leads})

# Scraper execution
if start_btn:
    if not queries_list or not locations_list:
        st.error("Please specify both search query and target location in the sidebar.")
    else:
        task_matrix = [(q, loc) for q in queries_list for loc in locations_list]
        st.session_state.task_list = task_matrix
        st.session_state.scraped_data = []
        st.session_state.results_by_task = {}
        st.session_state.current_status = "running"
        
        total_tasks = len(task_matrix)
        active_workers = min(parallel_workers, total_tasks)
        
        overall_progress_bar = st.progress(0)
        overall_status_header = st.empty()
        worker_dashboard = st.empty()
        table_placeholder = st.empty()
        
        event_queue = queue.Queue()
        all_leads_collector = []
        task_results_collector = {}
        worker_statuses = {}
        completed_count = 0
        start_time = time.time()
        
        update_status("running", f"Spinning up {active_workers} parallel session(s) across {total_tasks} task(s)...")
        
        with ThreadPoolExecutor(max_workers=active_workers) as executor:
            futures = [
                executor.submit(execute_worker_task, idx, t[0], t[1], lead_limit, headful, require_phone, event_queue)
                for idx, t in enumerate(task_matrix)
            ]
            
            while completed_count < total_tasks:
                has_event = False
                while not event_queue.empty():
                    has_event = True
                    evt = event_queue.get_nowait()
                    tid = evt.get("task_id")
                    mtype = evt.get("type")
                    
                    if mtype == "task_start":
                        worker_statuses[tid] = {
                            "query": evt["query"],
                            "location": evt["location"],
                            "status": "Connecting to Google Maps...",
                            "count": 0,
                            "done": False
                        }
                    elif mtype == "status":
                        if tid in worker_statuses:
                            worker_statuses[tid]["status"] = evt["message"]
                    elif mtype == "data":
                        item = evt["data"]
                        all_leads_collector.append(item)
                        st.session_state.scraped_data = all_leads_collector
                        if tid in worker_statuses:
                            worker_statuses[tid]["count"] += 1
                    elif mtype in ("task_done", "task_error"):
                        completed_count += 1
                        task_leads = evt.get("leads", [])
                        task_results_collector[(evt["query"], evt["location"])] = task_leads
                        if tid in worker_statuses:
                            worker_statuses[tid]["done"] = True
                            worker_statuses[tid]["status"] = "Completed" if mtype == "task_done" else f"Error: {evt.get('message')}"
                        
                        # Save individual task file immediately
                        if task_leads:
                            df_task = pd.DataFrame(task_leads)
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            safe_q = re.sub(r'[^a-zA-Z0-9]+', '-', evt['query'].lower().strip())
                            safe_loc = re.sub(r'[^a-zA-Z0-9]+', '-', evt['location'].lower().strip())
                            filename = f"leads_{timestamp}_Q-{safe_q}_L-{safe_loc}_R-{len(df_task)}.xlsx"
                            filepath = os.path.join(HISTORY_DIR, filename)
                            df_task.to_excel(filepath, index=False)
                
                if has_event:
                    # Update progress
                    pct = int((completed_count / total_tasks) * 100)
                    overall_progress_bar.progress(pct)
                    elapsed = int(time.time() - start_time)
                    overall_status_header.markdown(
                        f"### ⚡ Parallel Extraction: **{completed_count} of {total_tasks} tasks complete** • **{len(all_leads_collector)} total leads** ({elapsed}s elapsed)"
                    )
                    
                    # Render active worker cards
                    worker_html = ['<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 8px; margin-bottom: 1rem;">']
                    for tid, w_info in worker_statuses.items():
                        badge_color = "#10B981" if w_info["done"] else "#2563EB"
                        icon = "✅" if w_info["done"] else "⚡"
                        worker_html.append(f"""
                            <div class="worker-card">
                                <div style="display:flex; justify-content:space-between; font-weight:700;">
                                    <span>{icon} Session {tid+1}</span>
                                    <span style="color:{badge_color};">{w_info['count']} leads</span>
                                </div>
                                <div style="font-size:0.75rem; color:#64748B; margin: 2px 0;">{w_info['query']} • {w_info['location']}</div>
                                <div style="font-size:0.72rem; color:#475569; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{w_info['status']}</div>
                            </div>
                        """)
                    worker_html.append('</div>')
                    worker_dashboard.markdown("".join(worker_html), unsafe_allow_html=True)
                    
                    if all_leads_collector:
                        df_preview = pd.DataFrame(all_leads_collector)
                        table_placeholder.dataframe(df_preview, use_container_width=True)
                
                time.sleep(0.15)
                
        overall_progress_bar.progress(100)
        st.session_state.scraped_data = all_leads_collector
        st.session_state.results_by_task = task_results_collector
        st.session_state.current_status = "completed"
        
        total_time_str = f"{int(time.time() - start_time)}s"
        final_msg = f"Extraction complete! Successfully scraped {len(all_leads_collector)} leads across {total_tasks} search tasks in {total_time_str} using {active_workers} parallel sessions."
        st.session_state.current_message = final_msg
        update_status("completed", final_msg)
        
        # Save consolidated multi-sheet Excel file
        if all_leads_collector:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_filename = f"leads_{timestamp}_Q-multi_L-multi_R-{len(all_leads_collector)}.xlsx"
            batch_filepath = os.path.join(HISTORY_DIR, batch_filename)
            
            with pd.ExcelWriter(batch_filepath, engine='openpyxl') as writer:
                pd.DataFrame(all_leads_collector).to_excel(writer, sheet_name='All Leads', index=False)
                sheet_names = ['All Leads']
                for (q_name, l_name), leads_list in task_results_collector.items():
                    if leads_list:
                        raw_title = f"{l_name.split(',')[0]} - {q_name}"
                        s_name = clean_sheet_name(raw_title, sheet_names)
                        sheet_names.append(s_name)
                        pd.DataFrame(leads_list).to_excel(writer, sheet_name=s_name, index=False)
            st.toast(f"💾 Multi-sheet workbook saved: {batch_filename}", icon="💾")

# Download layout if leads are loaded
if st.session_state.scraped_data:
    df_final = pd.DataFrame(st.session_state.scraped_data)
    num_tasks = len(st.session_state.get("results_by_task", {}))
    
    st.markdown("---")
    st.markdown(f"### Results ({len(df_final)} Total Records Found across {num_tasks} Search Target(s))")
    st.dataframe(df_final, use_container_width=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    
    # 1. Multi-Sheet Excel
    with col_dl1:
        excel_multi_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_multi_buffer, engine='openpyxl') as writer:
            df_final.to_excel(writer, sheet_name='All Leads', index=False)
            sheet_names = ['All Leads']
            for (q_name, l_name), loc_leads in st.session_state.get("results_by_task", {}).items():
                if loc_leads:
                    raw_title = f"{l_name.split(',')[0]} - {q_name}"
                    s_name = clean_sheet_name(raw_title, sheet_names)
                    sheet_names.append(s_name)
                    pd.DataFrame(loc_leads).to_excel(writer, sheet_name=s_name, index=False)
                    
        st.markdown('<div class="download-btn">', unsafe_allow_html=True)
        st.download_button(
            label="📊 Download Multi-Sheet Excel",
            data=excel_multi_buffer.getvalue(),
            file_name=f"leads_multisheet_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown('</div>', unsafe_allow_html=True)
        
    # 2. Consolidated CSV
    with col_dl2:
        csv_data = df_final.to_csv(index=False).encode('utf-8')
        st.markdown('<div class="download-btn">', unsafe_allow_html=True)
        st.download_button(
            label="📄 Download All as CSV",
            data=csv_data,
            file_name=f"leads_consolidated_{timestamp}.csv",
            mime="text/csv"
        )
        st.markdown('</div>', unsafe_allow_html=True)
        
    # 3. ZIP Archive of individual Excels
    with col_dl3:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for (q_name, l_name), loc_leads in st.session_state.get("results_by_task", {}).items():
                if loc_leads:
                    loc_buf = io.BytesIO()
                    with pd.ExcelWriter(loc_buf, engine='openpyxl') as loc_writer:
                        pd.DataFrame(loc_leads).to_excel(loc_writer, sheet_name='Leads', index=False)
                    safe_task = re.sub(r'[^a-zA-Z0-9]+', '_', f"{q_name}_{l_name}".strip())
                    zf.writestr(f"leads_{safe_task}.xlsx", loc_buf.getvalue())
                    
        st.markdown('<div class="download-btn">', unsafe_allow_html=True)
        st.download_button(
            label="📦 Download All Excels (ZIP)",
            data=zip_buffer.getvalue(),
            file_name=f"leads_individual_excels_{timestamp}.zip",
            mime="application/zip"
        )
        st.markdown('</div>', unsafe_allow_html=True)

# Saved Leads & History Panel
st.markdown("---")
st.subheader("Saved Leads & History")

history_items = get_history()
if not history_items:
    st.markdown("""
        <div style="background-color: #F8FAFC; border: 1px dashed #E2E8F0; border-radius: 8px; padding: 2rem; text-align: center; font-size: 0.85rem; color: #64748B;">
            No previous lead extractions found in history.
        </div>
    """, unsafe_allow_html=True)
else:
    for idx, item in enumerate(history_items):
        filepath = os.path.join(HISTORY_DIR, item["filename"])
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                excel_bytes = f.read()
            
            with st.container():
                col_info, col_time, col_recs, col_dl = st.columns([3, 2, 1, 1.5])
                
                with col_info:
                    st.markdown(f"<span style='font-size:0.9rem; font-weight:600; color:#1E293B;'>🎯 {item['query']}</span><br><span style='font-size:0.75rem; color:#64748B;'>📍 {item['location']}</span>", unsafe_allow_html=True)
                
                with col_time:
                    st.markdown(f"<span style='font-size:0.8rem; color:#64748B; font-family:monospace; padding-top:0.4rem; display:block;'>🕒 {item['timestamp']}</span>", unsafe_allow_html=True)
                    
                with col_recs:
                    st.markdown(f"<span style='font-size:0.8rem; color:#1E293B; font-weight:600; padding-top:0.4rem; display:block;'>📊 {item['records']} leads</span>", unsafe_allow_html=True)
                    
                with col_dl:
                    st.download_button(
                        label="Download File",
                        data=excel_bytes,
                        file_name=item["filename"],
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"hist_dl_{idx}_{item['filename']}"
                    )
            st.markdown('<hr style="border-color:#F1F5F9; margin: 0.5rem 0;" />', unsafe_allow_html=True)
