from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import json
import time

# === Slack webhook URL – nahraď svou ===
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

# === Nastavení prohlížeče ===
options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(), options=options)

# === Načti stránku ===
driver.get("https://www.tetadrogerie.cz/")
wait = WebDriverWait(driver, 10)
actions = ActionChains(driver)

wait.until(EC.presence_of_element_located((By.CLASS_NAME, "c-main-menu__container")))
menu = driver.find_element(By.CLASS_NAME, "c-main-menu__container")
menu_items = menu.find_elements(By.TAG_NAME, "li")
menu_count = len(menu_items)

print(f"🧭 Načteno {menu_count} hlavních kategorií")

# === Hover a sběr odkazů ===
all_links = set()

for item in menu_items:
    try:
        actions.move_to_element(item).perform()
        time.sleep(0.5)
        links = item.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href")
            text = link.text.strip() or "(bez textu)"
            if href:
                all_links.add((text, href))
    except Exception as e:
        print(f"[⚠️] Nelze hovernout: {e}")

driver.quit()
print(f"\n🔗 Nasbíráno {len(all_links)} unikátních odkazů. Kontroluji ve 30 vláknech...\n")

# === Kontrola odkazů ===
status_counts = defaultdict(int)
results = []  # (text, href, status, status_type)

def check_link(link_data):
    text, href = link_data
    try:
        r = requests.get(href, timeout=25)
        code = r.status_code
        status_counts[code] += 1
        if code == 404:
            return (text, href, code, "404")
        elif code >= 500:
            return (text, href, code, "server_error")
        else:
            return (text, href, code, "ok")
    except requests.exceptions.Timeout:
        status_counts["timeout"] += 1
        return (text, href, "timeout", "timeout")
    except Exception as e:
        status_counts["chyba"] += 1
        return (text, href, "chyba", "error")

with ThreadPoolExecutor(max_workers=30) as executor:
    futures = [executor.submit(check_link, link) for link in all_links]
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        text, href, status, _ = result
        print(f"{status}: {text} → {href}")

# === Shrnutí ===
int_keys = {k: v for k, v in status_counts.items() if isinstance(k, int)}
str_keys = {k: v for k, v in status_counts.items() if isinstance(k, str)}

summary_lines = []
summary_lines.append(f"🧭 *Hlavních menu položek:* `{menu_count}`")
summary_lines.append(f"🔗 *Celkem kontrolováno odkazů:* `{len(results)}`")

for key in sorted(int_keys):
    summary_lines.append(f"`{key}`: {int_keys[key]}")
for key in sorted(str_keys):
    summary_lines.append(f"`{key}`: {str_keys[key]}")

# === Problémové odkazy ===
problematic = [r for r in results if r[3] in ["404", "server_error", "timeout", "error"]]

if problematic:
    summary_lines.append("\n❗ *Problémové odkazy:*")
    for text, href, status, _ in problematic[:20]:  # max 20 do Slacku
        display_text = f"{href} ({status})"
        summary_lines.append(f"- {display_text}")
    if len(problematic) > 20:
        summary_lines.append(f"...a dalších {len(problematic) - 20}")
else:
    summary_lines.append("\n✅ Žádné problémové odkazy.")

# === Odeslání do Slacku ===
payload = {
    "text": "\n".join(summary_lines)
}

try:
    response = requests.post(
        SLACK_WEBHOOK_URL,
        data=json.dumps(payload),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code == 200:
        print("✅ Shrnutí úspěšně odesláno do Slacku.")
    else:
        print(f"⚠️ Slack webhook selhal: {response.status_code} - {response.text}")
except Exception as e:
    print(f"⚠️ Chyba při odesílání do Slacku: {e}")
