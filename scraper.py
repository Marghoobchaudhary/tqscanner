import os
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class TitlequoteScanner:
    def __init__(self):
        self.EP_BASE_URL = "https://titlequote.stlmsd.com/#/"
        self.json_file_path = "tq_data.json"  # write in repo root

        # remove any previous output so git sees a fresh change
        if os.path.exists(self.json_file_path):
            os.remove(self.json_file_path)
            print(f"Deleted existing file: {self.json_file_path}")

        # headless Chrome (CI-friendly)
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
        self.wait = WebDriverWait(self.driver, 60)

        self.data = []

        # exact headers from the site (order matters)
        self.headers = [
            "Seller Name",
            "Service Address",
            "Zip Code",
            "Locator",
            "Quote ID",
            "Quote Amount",
            "Closing Date",
            "Stage",
            "Submitted By",
        ]

    def scrape(self):
        try:
            self.driver.get(self.EP_BASE_URL)
            self.driver.maximize_window()

            self.login()
            self.change_no_of_results()

            # paginate and collect
            while True:
                self.get_data()

                # paginator label looks like "1 – 100 of 367"
                range_el = self.driver.find_element(By.CLASS_NAME, "mat-mdc-paginator-range-label")
                parts = range_el.text.strip().split()
                current_max = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
                total_results = int(parts[-1]) if parts and parts[-1].isdigit() else 0
                print(f"Current: {current_max}, Total: {total_results}")

                if current_max < total_results:
                    self.next_page()
                else:
                    break

            self.write_json()
        except Exception as e:
            print(f"[ERROR] {e}")
            self.save_debug_artifacts()
            raise
        finally:
            self.driver.quit()

        return self.json_file_path

    def login(self):
        """
        Uses env vars TQ_USERNAME/TQ_PASSWORD if available.
        If not set (local/manual), pauses 30s so you can log in by hand.
        In GitHub Actions you should provide secrets for non-interactive login.
        """
        username = os.environ.get("TQ_USERNAME")
        password = os.environ.get("TQ_PASSWORD")

        if not username or not password:
            print("No TQ_USERNAME/TQ_PASSWORD set. Pausing 30s for manual login...")
            time.sleep(30)
            return

        self.wait.until(EC.presence_of_element_located((By.ID, "username")))
        self.driver.find_element(By.ID, "username").send_keys(username)
        self.driver.find_element(By.ID, "password").send_keys(password)

        # matches your earlier working approach
        self.driver.find_elements(By.CLASS_NAME, "ng-touched")[0].find_element(By.TAG_NAME, "button").click()
        print("Logged in.")
        time.sleep(15)  # give the SPA time to load

    def change_no_of_results(self):
        """Increase page size to reduce pagination (best-effort; safe to skip if controls change)."""
        try:
            self.wait.until(EC.presence_of_element_located((By.ID, "mat-select-0")))
            self.driver.find_element(By.ID, "mat-select-0").click()
            time.sleep(1)

            options_div = self.driver.find_element(By.ID, "mat-select-0-panel")
            options = options_div.find_elements(By.TAG_NAME, "mat-option")
            if options:
                options[-1].click()  # usually the largest page size
                print("Changed page size to max.")
            time.sleep(3)
        except Exception as e:
            print(f"Could not change page size: {e}")

    def get_data(self):
        """Scrape one page into records with the exact site headers as keys."""
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
        tbody = self.driver.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")

        added = 0
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < len(self.headers):
                continue  # skip incomplete rows (e.g., placeholders)

            record = {}
            for idx, header in enumerate(self.headers):
                record[header] = cells[idx].text.strip()

            # store only meaningful rows (need an identifier)
            if record.get("Quote ID") or record.get("Locator"):
                self.data.append(record)
                added += 1

        print(f"Scraped {len(rows)} rows from this page; added {added} records")

    def next_page(self):
        try:
            self.driver.find_element(By.CLASS_NAME, "mat-mdc-paginator-navigation-next").click()
            time.sleep(5)
        except Exception:
            print("Reached last page or couldn't click next.")

    def write_json(self):
        with open(self.json_file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.data)} records to {self.json_file_path}")

    def save_debug_artifacts(self):
        os.makedirs("artifacts", exist_ok=True)
        try:
            self.driver.save_screenshot("artifacts/error.png")
            with open("artifacts/page.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print("Saved screenshot and HTML in artifacts/")
        except Exception as e:
            print(f"Could not save debug artifacts: {e}")


if __name__ == "__main__":
    scanner = TitlequoteScanner()
    scanner.scrape()
