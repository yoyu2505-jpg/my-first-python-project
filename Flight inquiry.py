import sys
import os
import csv
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# --- 1. 工具函數 ---
def get_valid_date(prompt_text):
    while True:
        user_input = input(prompt_text).strip()
        try:
            datetime.strptime(user_input, '%Y-%m-%d')
            return user_input
        except ValueError:
            print("❌ 格式錯誤！請重新輸入 YYYY-MM-DD")

class TripFlightScraper:
    def __init__(self, dep_city, des_city, dep_date, ret_date):
        # 處理打包後的路徑，確保 CSV 產存在 .exe 旁邊
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        self.dep_city = dep_city
        self.des_city = des_city
        self.dep_date = dep_date
        self.ret_date = ret_date
        
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 15)
        self.wait_long = WebDriverWait(self.driver, 40)
        
        filename = f"trip_{dep_city}_{des_city}_{datetime.now().strftime('%m%d_%H%M')}.csv"
        self.csv_filename = os.path.join(application_path, filename)

    def _wait_for_loading_overlay(self):
        overlay_loc = (By.CLASS_NAME, "usp-loading-content")
        try:
            self.wait_long.until(EC.invisibility_of_element_located(overlay_loc))
            time.sleep(1)
        except: pass

    def _select_date_js(self, target_date):
        date_obj = datetime.strptime(target_date, '%Y-%m-%d')
        search_date = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
        for _ in range(12):
            js_script = f"var target='{search_date}';var cells=document.querySelectorAll('td[data-d]');for(var i=0;i<cells.length;i++){{var d=cells[i].getAttribute('data-d');if(d&&d.startsWith(target)){{cells[i].scrollIntoView({{block:'center'}});cells[i].click();return true;}}}}return false;"
            if self.driver.execute_script(js_script):
                time.sleep(1)
                return True
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, "span[aria-label*='下個'], .next-mon")
                self.driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(1.2)
            except: break
        return False

    def setup_search(self):
        print(f"📍 正在設定搜尋: {self.dep_city} -> {self.des_city}")
        self.driver.get("https://tw.trip.com/flights/?locale=zh-TW&curr=TWD")
        
        def enter_and_verify(city, wrapper_css, input_css, label):
            try:
                self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, wrapper_css))).click()
                field = self.driver.find_element(By.CSS_SELECTOR, input_css)
                field.send_keys(Keys.BACKSPACE *3 + city)
                time.sleep(1)
                option_xpath = f"//div[@data-testid='0']//span[contains(., '{city}')]"
                self.wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath))).click()
                return True
            except:
                print(f"❌ 錯誤：在{label}找不到 '{city}'")
                return False

        if not enter_and_verify(self.dep_city, "div[data-testid='search_city_from0_wrapper']", "input[data-testid='search_city_from0']", "出發地"): return False
        if not enter_and_verify(self.des_city, "div[data-testid='search_city_to0_wrapper']", "input[data-testid='search_city_to0']", "目的地"): return False

        dep_field = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[data-testid='search_date_depart0']")))
        self.driver.execute_script("arguments[0].click();", dep_field)
        if self._select_date_js(self.dep_date):
            time.sleep(1)
            self._select_date_js(self.ret_date)
            return True
        return False

    def scrape(self, max_main, max_sub):
        print("🚀 送出搜尋並等待結果...")
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='search_btn']"))).click()
        self._wait_for_loading_overlay()

        # 1. 這裡增加了那四個標籤的 Header
        headers = [
            '去程航空公司', '去程日期', '去程耗時', '去程出發', '去程出發機場', '去程抵達', '去程抵達機場', 
            '回程航空公司', '回程日期', '回程耗時', '回程出發', '回程出發機場', '回程抵達', '回程抵達機場', '價格'
        ]
        
        with open(self.csv_filename, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for i in range(max_main):
                print(f"\n🔄 [主方案 {i+1}/{max_main}] 操作中...")
                try:
                    self.wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-tracker-id="list_sortPanel_recommend"]')))
                    for _ in range(2): self.driver.execute_script("window.scrollBy(0, 500);"); time.sleep(0.5)
                    
                    main_btns = self.driver.find_elements(By.XPATH, "//button[@data-testid='u_select_btn']")
                    if i >= len(main_btns): break
                    
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", main_btns[i])
                    self.driver.execute_script("arguments[0].click();", main_btns[i])
                    self._wait_for_loading_overlay()

                    for j in range(max_sub):
                        try:
                            sub_btns = self.driver.find_elements(By.XPATH, "//button[@data-testid='u_select_btn']")
                            if j >= len(sub_btns): break
                            self.driver.execute_script("arguments[0].click();", sub_btns[j])
                            
                            p_el = self.wait_long.until(lambda d: d.find_element(By.CLASS_NAME, "o-price-flight__num"))
                            row = self._parse_flight_popup(p_el.get_attribute("innerText"))
                            writer.writerow(row)
                            print(f"      ✅ 抓取成功: {row[0]} | {row[-1]}")
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(0.8)
                        except: ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()

                    print("🔙 返回主列表...")
                    self.driver.back()
                    self._wait_for_loading_overlay()
                except: print(f"⚠️ 主方案 {i+1} 略過")

    def _parse_flight_popup(self, price):
        """解析彈窗內容，包含機場代碼與名稱"""
        airs = self.driver.find_elements(By.CLASS_NAME, "flight-info-airline-name")
        times = self.driver.find_elements(By.CLASS_NAME, "time")
        infos = self.driver.find_elements(By.CSS_SELECTOR, "span.ml-8.mr-8")
        
        # 2. 使用 data-testid 抓取機場資訊
        port_infos = self.driver.find_elements(By.CSS_SELECTOR, "span[data-testid='city-port-name-info']")
        
        def get_t(elements, idx):
            # 使用 innerText 確保抓到標籤內所有層級的文字
            return elements[idx].get_attribute("innerText").strip().replace('\n', ' ') if len(elements) > idx else "N/A"

        # 3. 按照 15 個欄位的順序回傳
        return [
            get_t(airs, 0),       # 去程航空公司
            get_t(infos, 0),      # 去程日期
            get_t(infos, 1),      # 去程耗時
            get_t(times, 0),      # 去程出發時間
            get_t(port_infos, 0), # 去程出發機場 🆕
            get_t(times, 1),      # 去程抵達時間
            get_t(port_infos, 1), # 去程抵達機場 🆕
            get_t(airs, 1),       # 回程航空公司
            get_t(infos, 2),      # 回程日期
            get_t(infos, 3),      # 回程耗時
            get_t(times, 2),      # 回程出發時間
            get_t(port_infos, 2), # 回程出發機場 🆕
            get_t(times, 3),      # 回程抵達時間
            get_t(port_infos, 3), # 回程抵達機場 🆕
            f"TWD {price}"
        ]

    def close(self):
        self.driver.quit()

# --- 2. 主程式無限循環區塊 (支援上一步) ---
if __name__ == "__main__":
    while True:
        print("\n" + "="*40)
        print("✈️  Trip.com 航班搜尋工具 (QA 自動化版)")
        print("="*40)

        data = {"dep": "", "des": "", "dep_date": "", "ret_date": "", "m_cnt": 3, "s_cnt": 3}
        step, cancel_all = 1, False

        while step <= 5:
            print(f"\n[步驟 {step}/5] (輸入 'b' 回上一步，輸入 'q' 退出)")
            if step == 1:
                val = input("🛫 請輸入出發地: ").strip()
                if val.lower() == 'q': cancel_all = True; break
                if not val: continue
                data["dep"] = val; step += 1
            elif step == 2:
                val = input(f"🛬 出發地為 [{data['dep']}]，請輸入目的地: ").strip()
                if val.lower() == 'q': cancel_all = True; break
                if val.lower() == 'b': step -= 1; continue
                if not val: continue
                data["des"] = val; step += 1
            elif step == 3:
                val = input("📅 去程日期 (YYYY-MM-DD): ").strip()
                if val.lower() == 'q': cancel_all = True; break
                if val.lower() == 'b': step -= 1; continue
                try: datetime.strptime(val, '%Y-%m-%d'); data["dep_date"] = val; step += 1
                except: print("❌ 格式錯誤！")
            elif step == 4:
                val = input("📅 回程日期 (YYYY-MM-DD): ").strip()
                if val.lower() == 'q': cancel_all = True; break
                if val.lower() == 'b': step -= 1; continue
                try: datetime.strptime(val, '%Y-%m-%d'); data["ret_date"] = val; step += 1
                except: print("❌ 格式錯誤！")
            elif step == 5:
                try:
                    m_in = input("🔢 抓取去程班機數 (預設 3，輸入 'b' 回上一步): ").strip()
                    if m_in.lower() == 'b': step -= 1; continue
                    data["m_cnt"] = int(m_in) if m_in else 3
                    
                    s_in = input("🔢 抓取回程班機數 (預設 3): ").strip()
                    if s_in.lower() == 'b': continue # 這裡維持在原步驟重新輸入去程
                    data["s_cnt"] = int(s_in) if s_in else 3
                    
                    step += 1 # 兩個都輸入完才進到下一步
                except:
                    print("❌ 請輸入數字。")

        if cancel_all: break
        scraper = TripFlightScraper(data["dep"], data["des"], data["dep_date"], data["ret_date"])
        try:
            if scraper.setup_search():
                scraper.scrape(max_main=data["m_cnt"], max_sub=data["s_cnt"])
                print(f"\n✨ 任務完成！檔案: {scraper.csv_filename}")
        except Exception as e: print(f"❌ 發生錯誤: {e}")
        finally: scraper.close()

        if input("\n💡 是否要抓取下一組？(y/n): ").lower() != 'y': break