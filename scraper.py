import urllib.parse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import re
import time

def extract_city(address, search_location):
    """
    Extracts the city name from the business address using heuristics
    and comparing with the search location.
    """
    if not address:
        return search_location.split(',')[0].strip()
    
    parts = [p.strip() for p in address.split(',') if p.strip()]
    if not parts:
        return search_location.split(',')[0].strip()
    
    # 1. Check if the search location city is explicitly in the address parts
    search_city = search_location.split(',')[0].strip()
    for part in parts:
        if search_city.lower() in part.lower():
            # Returns the formatted search city (e.g. Surat instead of surat)
            return search_city
            
    # 2. Heuristic: Usually city is the second to last part of the address
    # (e.g., "Piplod, Surat, Gujarat 395007" -> parts are [... "Piplod", "Surat", "Gujarat 395007"])
    if len(parts) >= 2:
        # Check if the last part is a postal code / state combination
        last_part = parts[-1]
        # If last part contains numbers (like postal code), the city is likely parts[-2]
        if any(c.isdigit() for c in last_part):
            return parts[-2]
        else:
            return parts[-1]
            
    return parts[0]

def scrape_google_maps(query, location, max_results, headful=False):
    """
    Scrapes business listings from Google Maps.
    Yields dictionary results in real-time.
    """
    search_query = f"{query} in {location}"
    encoded_query = urllib.parse.quote_plus(search_query)
    search_url = f"https://www.google.com/maps/search/{encoded_query}"
    
    with sync_playwright() as p:
        # Launch browser with auto-installation fallback for free cloud environments
        browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
        try:
            browser = p.chromium.launch(headless=not headful, args=browser_args)
        except Exception as launch_err:
            err_str = str(launch_err)
            if "Executable doesn't exist" in err_str or "playwright install" in err_str:
                yield {"type": "status", "message": "First-time setup: Installing browser binaries in cloud (takes ~1 min)..."}
                import subprocess
                subprocess.run(["playwright", "install", "chromium"], check=True)
                browser = p.chromium.launch(headless=not headful, args=browser_args)
            else:
                raise launch_err

        
        # Create a new browser context with English language settings to ensure consistent text selectors
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        stealth = Stealth()
        stealth.apply_stealth_sync(context)
        
        yield {"type": "status", "message": f"Navigating to Google Maps search..."}
        
        try:
            page.goto(search_url, timeout=60000)
            page.wait_for_timeout(3000)
        except Exception as e:
            yield {"type": "error", "message": f"Failed to load search page: {str(e)}"}
            browser.close()
            return
            
        # Detect if we have a results feed or if we were redirected to a single listing
        feed_locator = page.locator('div[role="feed"]').first
        
        urls = set()
        
        if feed_locator.count() > 0:
            yield {"type": "status", "message": "Scrolling search results to collect listings..."}
            
            scroll_attempts = 0
            max_scroll_attempts = max(40, (max_results // 5))
            last_url_count = 0
            
            while len(urls) < max_results and scroll_attempts < max_scroll_attempts:
                # Find all place links
                links = page.locator('a[href*="/maps/place/"]').all()
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            # Parse out clean URL
                            clean_url = href.split('?')[0]
                            if clean_url not in urls:
                                urls.add(clean_url)
                                if len(urls) >= max_results:
                                    break
                    except Exception:
                        continue
                
                if len(urls) >= max_results:
                    break
                    
                # Scroll down feed
                feed_locator.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(2000)
                
                # Check for "reached the end" indicators
                end_text_visible = (
                    page.get_by_text("You've reached the end of the list").is_visible() or
                    page.get_by_text("No more results").is_visible()
                )
                if end_text_visible:
                    yield {"type": "status", "message": "Reached the end of Google Maps results."}
                    break
                    
                # Check if we are stuck and not getting new URLs
                if len(urls) == last_url_count:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0
                    last_url_count = len(urls)
                    
            yield {"type": "status", "message": f"Found {len(urls)} listings. Starting detailed scraping..."}
        else:
            # Maybe single place redirect
            current_url = page.url
            if "/maps/place/" in current_url:
                clean_url = current_url.split('?')[0]
                urls.add(clean_url)
                yield {"type": "status", "message": "Redirected directly to single business listing."}
            else:
                yield {"type": "error", "message": "No search results found. Try adjusting your query."}
                browser.close()
                return

        # Visit each business listing URL and scrape details
        scraped_count = 0
        for i, url in enumerate(list(urls)[:max_results]):
            yield {"type": "status", "message": f"Processing listing {i+1} of {len(urls)}..."}
            
            try:
                page.goto(url, timeout=30000)
                page.wait_for_timeout(1500)
                
                # Wait for title to load (essential check)
                try:
                    page.wait_for_selector('h1', timeout=8000)
                except Exception:
                    yield {"type": "status", "message": f"Skipping listing {i+1} (details failed to load)"}
                    continue
                
                # Check if permanently closed
                is_closed = False
                closed_indicators = ["Permanently closed", "Permanently Closed"]
                for indicator in closed_indicators:
                    if page.get_by_text(indicator).is_visible():
                        is_closed = True
                        break
                        
                if is_closed:
                    yield {
                        "type": "skip", 
                        "message": f"Skipped: Permanently closed listing detected."
                    }
                    continue
                
                # Name
                name = ""
                name_el = page.locator('h1').first
                if name_el.count() > 0:
                    name = name_el.inner_text().strip()
                
                # Address
                address = ""
                address_el = page.locator('[data-item-id="address"]').first
                if address_el.count() > 0:
                    address = address_el.inner_text().strip()
                    # Clean up address formatting and remove Google Maps pin icon
                    address = address.replace('\ue0c8', '').replace('\n', ' ').strip()
                
                # Phone number
                phone = ""
                phone_el = page.locator('[data-item-id^="phone:tel:"]').first
                if phone_el.count() > 0:
                    phone = phone_el.inner_text().strip()
                    # Clean up phone (remove "Phone: " or other prefixes if any)
                    phone = re.sub(r'[^\d+\s\-()]+', '', phone).strip()
                
                # City
                city = extract_city(address, location)
                
                # Return business info
                scraped_count += 1
                yield {
                    "type": "data",
                    "data": {
                        "Name": name,
                        "Mobile Number": phone if phone else "N/A",
                        "Address": address if address else "N/A",
                        "City": city,
                        "Google Maps URL": url
                    }
                }
                
            except Exception as e:
                yield {"type": "status", "message": f"Error scraping details for listing {i+1}: {str(e)}"}
                continue
                
        yield {"type": "complete", "message": f"Scraping complete. Successfully scraped {scraped_count} listings!"}
        browser.close()
