import requests
import json
import time
import os
import dotenv

dotenv.load_dotenv()

API_KEY = os.getenv("CUSTOM_SEARCH_API_KEY")
CX = os.getenv("CUSTOM_SEARCH_ENGINE_ID")

def google_search_person(person_name, num_pages=1, pause=1.5):
    """
    Fetches public info about a person using Google Custom Search JSON API.
    Returns aggregated JSON with:
    - texts: list of snippets or content
    - links: list of URLs
    """

    texts = []
    links = []

    for page in range(num_pages):
        start = page * 10 + 1
        params = {
            "key": API_KEY,
            "cx": CX,
            "q": person_name,
            "start": start
        }
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params)
        data = response.json()

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            if snippet and link:
                texts.append(snippet)
                links.append(link)

        time.sleep(pause)

    result_json = {
        "query": person_name,
        "total_results": len(links),
        "texts": texts,
        "links": links
    }

    return result_json


if __name__ == "__main__":
    person = input("Enter a person's name: ")
    info = google_search_person(person)

    # Save to JSON file
    output_file = f"{person.replace(' ', '_')}_info.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=4)

    print(f"\n✅ Saved results to {output_file}")
    print(f"🔗 {info['total_results']} results found.")
