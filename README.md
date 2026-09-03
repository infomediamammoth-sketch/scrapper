# scrapper

A high-performance Google Business Listings and Leads Scraper built with Python, Playwright, and Streamlit.

## Features
- **Google Maps Data Scraping**: Extracts Business Name, Mobile Number, Address, City, and Maps URL.
- **Automated Filtering**: Automatically detects and skips permanently closed businesses.
- **Batch Location Queueing**: Queue multiple cities/regions to scrape sequentially in one run.
- **Multi-Sheet Excel Export**: Generates an Excel workbook with an "All Leads" master tab and dedicated sheets for each location.
- **Export Options**: Download as multi-sheet Excel (.xlsx), consolidated CSV, or individual Excels (.zip).
- **History Tracking**: Keeps a history log of all completed runs.

---

## 🚀 Cloud Deployment Guide

This project includes a production-ready `Dockerfile` and can be deployed with 1 click to any cloud container host.

### Option 1: Deploy on Railway (Recommended)
1. Go to [Railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** > **Deploy from GitHub repo**.
3. Select this `scrapper` repository.
4. Railway will automatically detect the `Dockerfile` and build it.
5. In your Railway service settings under **Networking**, click **Generate Domain**.
6. Open your public URL and start scraping from any device!

### Option 2: Deploy on Render
1. Go to [Render.com](https://render.com) and create a free account.
2. Click **New +** > **Web Service**.
3. Connect your `scrapper` GitHub repository.
4. Select **Docker** as the environment.
5. Click **Create Web Service**. Once deployed, your app will be live at `https://your-app.onrender.com`.

---

## 💻 Local Usage

### Quick Start (Windows)
Double-click `run_app.bat` or the desktop shortcut to launch in standalone App mode.

### Manual Run
```bash
pip install -r requirements.txt
playwright install --with-deps chromium
streamlit run app.py
```
