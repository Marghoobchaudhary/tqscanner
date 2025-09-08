from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import os
import re
from FileManager import create_output_dir

def _clean_currency(val: str) -> str:
    """'$12,345.67' -> '12345.67'; empty string if no digits."""
    if val is None:
        return ""
    s = str(val).strip()
    s = s.replace("$", "").replace(",", " ")
    s = re.sub(r"\s+", "", s)
    return s if re.search(r"\d", s) else ""

class TitlequoteScanner:
    def __init__(self):
        self.EP_BASE_URL = "https://titlequote.stlmsd.com/#/"
        self.output_directory_name = "TitlequoteScanner-Output"
        self.json_file_path = f"output/{self.output_directory_name}/tq_data.json"

        # ensure output/TitlequoteScanner-Output exists & clean old JSON
        create_output_dir(self.output_directory_name)
        if os.path.exists(self.json_file_path):
            try:
                os.remove(self.json_file_path)
                print(f"Deleted existing file: {self.json_file_path}")
            except OSError as e:
                print(f"Error deleting file: {e}")

        # Headless Chrome in CI
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless=new")

        # if a Chrome binary path is provided by the runner, use it
        chrome_path = os.environ.get("CHROME_PATH") or os.environ.get("GOOGLE_CHROME_SHIM")
        if chrome_path:
            options.binary_location = chrome_path

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 60)

        self.data = []

    def scrape(self):
        self.driver.get(self.EP_BASE_URL)
        self.driver.maximize_window()

        self.login()
        self.change_no_of_results()

        # Scrape all pages
        while True:
            self.get_data()

            # paginator text like: "1 – 100 of 367"
            range_el = self.driver.find_element(By.CLASS_NAME, "mat-mdc-paginator-range-label")
            parts = range_el.text.strip().split()
            # Defensive parse
            current_max = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
            total_results = int(parts[-1]) if parts and parts[-1].isdigit() else 0
            print(f"Current: {current_max}, Total: {total_results}")

            if current_max < total_results:
                self.next_page()
            else:
                break

        self.append_to_json()
        self.driver.quit()
        return self.json_file_path

    def login(self):
        """
        Use env vars TQ_USERNAME/TQ_PASSWORD if present; otherwise wait 30s to allow manual login (local runs).
        In GitHub Actions you MUST set secrets for non-interactive login.
        """
        USERNAME = os.environ.get("TQ_USERNAME")
        PASSWORD = os.environ.get("TQ_PASSWORD")

        if not USERNAME or not PASSWORD:
            print("No TQ_USERNAME/TQ_PASSWORD env vars. Pausing 30s for manual login (local use).")
            time.sleep(30)
            return

        self.wait.until(EC.presence_of_element_located((By.ID, "username")))
        self.driver.find_element(By.ID, "username").send_keys(USERNAME)
        self.driver.find_element(By.ID, "password").send_keys(PASSWORD)

        # Click login button inside the first .ng-touched container (matches your working code)
        self.driver.find_elements(By.CLASS_NAME, "ng-touched")[0].find_element(By.TAG_NAME, "button").click()
        print("Logged in.")
        time.sleep(15)  # allow SPA to finish booting

    def change_no_of_results(self):
        """Open per-page dropdown and select the largest page size."""
        try:
            self.wait.until(EC.presence_of_element_located((By.ID, "mat-select-0")))
            self.driver.find_element(By.ID, "mat-select-0").click()
            time.sleep(1)

            options_div = self.driver.find_element(By.ID, "mat-select-0-panel")
            options = options_div.find_elements(By.TAG_NAME, "mat-option")
            if options:
                options[-1].click()  # largest page size
                print("Changed page size to max.")
            time.sleep(3)
        except Exception as e:
            print(f"Could not change page size: {e}")

    def get_data(self):
        """
        Map visible columns to your unified schema with empty strings for missing data:
        {
          "Trustee": "TitleQuote",
          "Sale_date": <Closing Date>,
          "Sale_time": "",
          "FileNo": <Quote ID (fallback Locator)>,
          "PropAddress": <Service Address>,
          "PropCity": "",
          "PropZip": <Zip Code>,
          "County": "",
          "OpeningBid": <Quote Amount normalized>,
          "vendor": "",
          "status- DROP DOWN": <Stage>,
          "Foreclosure Status": ""
        }
        """
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
        tbody = self.driver.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")

        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")

            def cell_txt(idx):
                return cells[idx].text.strip() if 0 <= idx < len(cells) else ""

            # Page columns:
            # 0 Seller Name | 1 Service Address | 2 Zip Code | 3 Locator | 4 Quote ID
            # 5 Quote Amount | 6 Closing Date | 7 Stage | 8 Submitted By
            service_address = cell_txt(1)
            zip_code = cell_txt(2)
            locator = cell_txt(3)
            quote_id = cell_txt(4)
            quote_amount = cell_txt(5)
            closing_date = cell_txt(6)
            stage = cell_txt(7)

            rec = {
                "Trustee": "TitleQuote",
                "Sale_date": closing_date or "",
                "Sale_time": "",
                "FileNo": quote_id or locator or "",
                "PropAddress": service_address or "",
                "PropCity": "",
                "PropZip": zip_code or "",
                "County": "",
                "OpeningBid": _clean_currency(quote_amount),
                "vendor": "",
                "status- DROP DOWN": stage or "",
                "Foreclosure Status": "",
            }

            if rec["FileNo"]:
                self.data.append(rec)

        print(f"Scraped {len(rows)} row
