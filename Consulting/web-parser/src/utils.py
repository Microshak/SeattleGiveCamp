def fetch_html(url):
    import requests
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def clean_url(url):
    return url.strip() if url else None