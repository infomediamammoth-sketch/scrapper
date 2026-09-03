---
title: Scrapper
emoji: 🦀
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8501
pinned: false
license: mit
---

# scrapper

A high-performance Google Business Listings and Leads Scraper built with Python, Playwright, and Streamlit.

## Features
- **Google Maps Data Scraping**: Extracts Business Name, Mobile Number, Address, City, and Maps URL.
- **Automated Filtering**: Automatically detects and skips permanently closed businesses.
- **Batch Location Queueing**: Queue multiple cities/regions to scrape sequentially in one run.
- **Multi-Sheet Excel Export**: Generates an Excel workbook with an "All Leads" master tab and dedicated sheets for each location.
- **Export Options**: Download as multi-sheet Excel (.xlsx), consolidated CSV, or individual Excels (.zip).
- **History Tracking**: Keeps a history log of all completed runs.
