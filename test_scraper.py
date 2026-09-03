from scraper import scrape_google_maps

def test():
    print("Testing Google Maps Scraper...")
    query = "Event Planners"
    location = "Bardoli, Gujarat"
    max_results = 2
    
    print(f"Searching for '{query}' in '{location}' (limit: {max_results})...\n")
    
    generator = scrape_google_maps(query, location, max_results, headful=False)
    
    for event in generator:
        if event["type"] == "status":
            print(f"[STATUS] {event['message']}")
        elif event["type"] == "skip":
            print(f"[SKIP] {event['message']}")
        elif event["type"] == "error":
            print(f"[ERROR] {event['message']}")
        elif event["type"] == "data":
            print(f"\n[DATA FOUND] {event['data']}\n")
        elif event["type"] == "complete":
            print(f"[COMPLETE] {event['message']}")

if __name__ == "__main__":
    test()
