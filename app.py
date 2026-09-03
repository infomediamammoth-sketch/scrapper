import streamlit as st
import pandas as pd
import io
import os
import re
import datetime
import time
import zipfile
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

# Helper to sanitize sheet names for Excel (max 31 chars, no special chars)
def clean_sheet_name(name, existing_names):
    cleaned = re.sub(r'[\\/*?:\[\]]', '', name).strip()
    cleaned = cleaned.split(',')[0].strip() # Use main city name
    if not cleaned:
        cleaned = "Location"
    cleaned = cleaned[:28]
    candidate = cleaned
    counter = 1
    while candidate.lower() in [e.lower() for e in existing_names]:
        candidate = f"{cleaned[:25]}_{counter}"
        counter += 1
    return candidate

# Helper to retrieve saved runs
def get_history():
    if not os.path.exists(HISTORY_DIR):
        return []
    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".xlsx") and f.startswith("leads_")]
    files.sort(reverse=True) # Newest runs first
    
    history_list = []
    for file in files:
        # Pattern: leads_{timestamp}_Q-{safe_query}_L-{safe_location}_R-{records}.xlsx
        match = re.search(r"leads_(\d{8}_\d{6})_Q-(.*)_L-(.*)_R-(\d+)\.xlsx", file)
        if match:
            ts_raw = match.group(1)
            q_raw = match.group(2).replace("-", " ").title()
            loc_raw = match.group(3).replace("-", " ").title()
            recs = match.group(4)
            
            # Format timestamp
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
    
    /* Font family settings */
    html, body, .stApp, p, span, div, label, input, button, select, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Clean white background */
    .stApp {
        background-color: #FFFFFF !important;
    }
    
    /* Left sidebar layout overrides */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
        width: 340px !important;
    }
    
    /* Sidebar headers and typography */
    section[data-testid="stSidebar"] h2 {
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        color: #1E293B !important;
        margin-bottom: 0.8rem !important;
    }
    
    section[data-testid="stSidebar"] label p {
        font-weight: 600 !important;
        color: #475569 !important;
        font-size: 0.85rem !important;
    }
    
    /* Blue primary button (Start Scraping) */
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
        height: 42px !important;
        transition: all 0.2s ease !important;
    }
    button[data-testid="stBaseButton-primary"]:hover {
        background-color: #1D4ED8 !important;
    }
    
    /* Green download buttons */
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
    
    /* Adjust main content widths */
    .block-container {
        max-width: 1200px !important;
        padding-top: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# SIDEBAR: Configuration Area
with st.sidebar:
    st.markdown("## Configuration")
    
    query = st.text_input("What to search for?", value="Event Planners", placeholder="e.g. Dentists, Event planners")
    
    loc_mode = st.radio("Location Mode", ["Single Location", "Multiple Locations (Queue)"], horizontal=True)
    
    if loc_mode == "Single Location":
        location = st.text_input("From where to search?", value="Surat, Gujarat", placeholder="e.g. Surat, Gujarat")
        locations_list = [location.strip()] if location.strip() else []
    else:
        locations_raw = st.text_area(
            "Locations Queue (one per line or comma-separated):",
            value="Surat, Gujarat\nBardoli, Gujarat\nNavsari, Gujarat",
            height=130,
            help="Enter each city or area on a new line or separated by commas."
        )
        raw_split = re.split(r'[\n,]+', locations_raw)
        locations_list = [loc.strip() for loc in raw_split if loc.strip()]
        if locations_list:
            st.caption(f"📋 **{len(locations_list)} location(s) in queue**")
    
    lead_limit = st.slider("Max Results to Scrape (per location)", min_value=10, max_value=1000, value=200, step=10)
    
    st.markdown("---")
    st.markdown("## Debugging Options")
    headful = st.checkbox("Show Browser (Headful)", value=False, help="Check this to watch the automation scroll Google Maps live.")
    
    st.markdown("---")
    
    # Information Box
    st.info("Note: This tool skips any listing detected as 'Permanently closed' automatically.")
    
    # Start Scraping Button
    start_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# MAIN AREA: Headers
st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 0.5rem;">
        <h1 style="font-size: 2.2rem; font-weight: 800; color: #0F172A; margin: 0;">🔍 Google Business Listing Scraper</h1>
    </div>
    <p style="font-size: 1.05rem; color: #475569; margin-bottom: 2rem;">A lightweight, local tool to extract lead lists from Google Maps business profiles.</p>
""", unsafe_allow_html=True)

# Initial state variables
if "current_status" not in st.session_state:
    st.session_state.current_status = "idle"
if "current_message" not in st.session_state:
    st.session_state.current_message = "Ready to scrape leads. Click 'Start Scraping' in the sidebar to begin."
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = []
if "location_data" not in st.session_state:
    st.session_state.location_data = {}
if "is_batch" not in st.session_state:
    st.session_state.is_batch = False
if "active_query" not in st.session_state:
    st.session_state.active_query = "leads"

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

# Scraper execution
if start_btn:
    if not query or not locations_list:
        st.error("Please specify both what to search and at least one target location in the sidebar.")
    else:
        st.session_state.scraped_data = []
        st.session_state.location_data = {}
        is_multi = len(locations_list) > 1
        st.session_state.is_batch = is_multi
        st.session_state.active_query = query
        
        queue_progress_bar = st.progress(0) if is_multi else None
        queue_status_header = st.empty()
        status_box = st.empty()
        table_placeholder = st.empty()
        
        all_scraped_list = []
        location_data = {}
        total_locs = len(locations_list)
        start_overall_time = time.time()
        
        st.session_state.current_status = "running"
        
        for loc_idx, current_loc in enumerate(locations_list):
            if is_multi:
                queue_pct = int((loc_idx / total_locs) * 100)
                queue_progress_bar.progress(queue_pct)
                queue_status_header.markdown(f"#### 📍 Processing Location {loc_idx + 1} of {total_locs}: **{current_loc}**")
            
            loc_scraped = []
            loc_start_time = time.time()
            
            try:
                msg = f"Connecting to Google Maps for '{query}' in '{current_loc}'..."
                update_status("running", msg)
                status_box.info(f"⚙️ [{current_loc}] {msg}")
                
                for event in scrape_google_maps(query, current_loc, lead_limit, headful):
                    elapsed_loc_str = f"{int(time.time() - loc_start_time)}s"
                    
                    if event["type"] == "status":
                        update_status("running", f"[{current_loc}] {event['message']}")
                        status_box.info(f"⚙️ [{current_loc}] {event['message']}")
                    elif event["type"] == "skip":
                        status_box.warning(f"⚠️ [{current_loc}] {event['message']}")
                    elif event["type"] == "error":
                        status_box.error(f"❌ [{current_loc}] {event['message']}")
                    elif event["type"] == "data":
                        item = dict(event["data"])
                        if is_multi:
                            item["Searched Location"] = current_loc
                        loc_scraped.append(item)
                        all_scraped_list.append(item)
                        st.session_state.scraped_data = all_scraped_list
                        
                        live_msg = f"[{current_loc}] Scraped {len(loc_scraped)} leads (Total across queue: {len(all_scraped_list)}). Time: {elapsed_loc_str}"
                        update_status("running", live_msg)
                        
                        df_preview = pd.DataFrame(all_scraped_list)
                        table_placeholder.dataframe(df_preview, use_container_width=True)
                    elif event["type"] == "complete":
                        status_box.success(f"✅ [{current_loc}] Finished: {len(loc_scraped)} leads extracted.")
                
                location_data[current_loc] = loc_scraped
                
                # Automatically save individual Excel file for this location in history
                if loc_scraped:
                    df_single = pd.DataFrame(loc_scraped)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_query = re.sub(r'[^a-zA-Z0-9]+', '-', query.lower().strip())
                    safe_location = re.sub(r'[^a-zA-Z0-9]+', '-', current_loc.lower().strip())
                    filename = f"leads_{timestamp}_Q-{safe_query}_L-{safe_location}_R-{len(df_single)}.xlsx"
                    filepath = os.path.join(HISTORY_DIR, filename)
                    df_single.to_excel(filepath, index=False)
                    
            except Exception as e:
                status_box.error(f"Error scraping {current_loc}: {str(e)}")
                location_data[current_loc] = loc_scraped

        if is_multi:
            queue_progress_bar.progress(100)
            queue_status_header.markdown(f"#### ✅ Finished all {total_locs} queued locations!")
            
        st.session_state.location_data = location_data
        st.session_state.scraped_data = all_scraped_list
        st.session_state.current_status = "completed"
        total_time_str = f"{int(time.time() - start_overall_time)}s"
        final_msg = f"Extraction complete! Total {len(all_scraped_list)} leads scraped across {len(locations_list)} location(s) in {total_time_str}."
        st.session_state.current_message = final_msg
        update_status("completed", final_msg)
        
        # Save consolidated multi-sheet Excel file if multiple locations
        if is_multi and all_scraped_list:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_query = re.sub(r'[^a-zA-Z0-9]+', '-', query.lower().strip())
            batch_filename = f"leads_{timestamp}_Q-{safe_query}_L-batch-{len(locations_list)}-locations_R-{len(all_scraped_list)}.xlsx"
            batch_filepath = os.path.join(HISTORY_DIR, batch_filename)
            
            with pd.ExcelWriter(batch_filepath, engine='openpyxl') as writer:
                pd.DataFrame(all_scraped_list).to_excel(writer, sheet_name='All Leads', index=False)
                sheet_names = ['All Leads']
                for loc_name, leads_list in location_data.items():
                    if leads_list:
                        s_name = clean_sheet_name(loc_name, sheet_names)
                        sheet_names.append(s_name)
                        pd.DataFrame(leads_list).to_excel(writer, sheet_name=s_name, index=False)
            st.toast(f"💾 Multi-sheet workbook saved: {batch_filename}", icon="💾")

# Download layout if leads are loaded
if st.session_state.scraped_data:
    df_final = pd.DataFrame(st.session_state.scraped_data)
    is_multi = st.session_state.get("is_batch", False) and len(st.session_state.get("location_data", {})) > 1
    safe_q = re.sub(r'[^a-zA-Z0-9]+', '_', st.session_state.get("active_query", "leads").lower().strip())
    
    st.markdown("---")
    if is_multi:
        st.markdown(f"### Results ({len(df_final)} Total Records across {len(st.session_state.location_data)} Locations)")
    else:
        st.markdown(f"### Results ({len(df_final)} Records Found)")
        
    st.dataframe(df_final, use_container_width=True)
    
    if is_multi:
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        
        # 1. Multi-Sheet Excel
        with col_dl1:
            excel_multi_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_multi_buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, sheet_name='All Leads', index=False)
                sheet_names = ['All Leads']
                for loc_name, loc_leads in st.session_state.location_data.items():
                    if loc_leads:
                        s_name = clean_sheet_name(loc_name, sheet_names)
                        sheet_names.append(s_name)
                        pd.DataFrame(loc_leads).to_excel(writer, sheet_name=s_name, index=False)
                        
            st.markdown('<div class="download-btn">', unsafe_allow_html=True)
            st.download_button(
                label="📊 Download Multi-Sheet Excel",
                data=excel_multi_buffer.getvalue(),
                file_name=f"leads_{safe_q}_multisheet_{len(st.session_state.location_data)}_locations.xlsx",
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
                file_name=f"leads_{safe_q}_consolidated.csv",
                mime="text/csv"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 3. ZIP Archive of individual Excels
        with col_dl3:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for loc_name, loc_leads in st.session_state.location_data.items():
                    if loc_leads:
                        loc_buf = io.BytesIO()
                        with pd.ExcelWriter(loc_buf, engine='openpyxl') as loc_writer:
                            pd.DataFrame(loc_leads).to_excel(loc_writer, sheet_name='Leads', index=False)
                        loc_clean_file = re.sub(r'[^a-zA-Z0-9]+', '_', loc_name.strip())
                        zf.writestr(f"leads_{safe_q}_{loc_clean_file}.xlsx", loc_buf.getvalue())
                        
            st.markdown('<div class="download-btn">', unsafe_allow_html=True)
            st.download_button(
                label="📦 Download All Excels (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"leads_{safe_q}_individual_excels.zip",
                mime="application/zip"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
    else:
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv_data = df_final.to_csv(index=False).encode('utf-8')
            st.markdown('<div class="download-btn">', unsafe_allow_html=True)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"leads_{safe_q}.csv",
                mime="text/csv"
            )
            st.markdown('</div>', unsafe_allow_html=True)
        with col_dl2:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Leads')
            
            st.markdown('<div class="download-btn">', unsafe_allow_html=True)
            st.download_button(
                label="Download Excel",
                data=excel_buffer.getvalue(),
                file_name=f"leads_{safe_q}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
