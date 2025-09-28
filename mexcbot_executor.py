import time
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEBUGGER_ADDR = "127.0.0.1:9222"
# COMPLETE_MESSAGE = 'の注文が全て約定しました'
COMPLETE_MESSAGE = 'order filled completely'

class SeleniumBot():
    def __init__(self, debugger_addr: str = DEBUGGER_ADDR):
        opts = ChromeOptions(); opts.debugger_address = debugger_addr
        self.driver = webdriver.Chrome(options=opts)
        self.wait = WebDriverWait(self.driver, 10)
        self.clickable = EC.element_to_be_clickable
        self.visibility = EC.visibility_of_element_located

    def set_qty(self, qty: float, mode: int = 1) -> bool:
        '''
        mode:1 右側のQuantity 
        mode:2 下部のQuantity 
        '''
        if mode == 1:
            selector = '#mexc_contract_v_open_position div.input-wrapper > div.extend-wrapper > input.ant-input'
        else:
            selector = 'input[id^=rc_select_]'
        try:
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.send_keys(Keys.CONTROL + "a")  # 全選択
            time.sleep(0.1)
            element.send_keys(Keys.DELETE)         # 削除
            time.sleep(0.1)
            element.send_keys(str(qty))
            actions = ActionChains(self.driver)
            actions.send_keys(Keys.TAB)
            actions.perform()
            if element.get_attribute('value') == str(qty):
                return True
            else:
                print(f'入力値が一致しません')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def open_long(self) -> bool:
        try:
            # Open Long ボタンをクリックする
            selector = 'button[data-testid="contract-trade-open-long-btn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            # 完了メッセージ確認
            selector = 'div.ant-notification-notice-message'
            element = self.wait.until(self.visibility((By.CSS_SELECTOR, selector)))
            if COMPLETE_MESSAGE in element.text.strip():
                print('注文が全て約定しました')
                return True
            else:
                print(f'成功トーストを検知できませんでした')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')

    def open_short(self) -> bool:
        try:
            # Open Short ボタンをクリックする
            selector = 'button[data-testid="contract-trade-open-short-btn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            # 完了メッセージ確認
            selector = 'div.ant-notification-notice-message'
            element = self.wait.until(self.visibility((By.CSS_SELECTOR, selector)))
            if COMPLETE_MESSAGE in element.text.strip():
                print('注文が全て約定しました')
                return True
            else:
                print(f'成功トーストを検知できませんでした')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def close_long(self) -> bool:
        try:
            # Close Long ボタンをクリックする
            selector = 'div[class^="FastClose_short"] button[class^="FastClose_closeBtn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            if COMPLETE_MESSAGE in element.text.strip():
                print('注文が全て約定しました')
                return True
            else:
                print(f'成功トーストを検知できませんでした')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def close_short(self) -> bool:
        try:
            # Close Long ボタンをクリックする
            selector = 'div[class^="FastClose_long"] button[class^="FastClose_closeBtn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            if COMPLETE_MESSAGE in element.text.strip():
                print('注文が全て約定しました')
                return True
            else:
                print(f'成功トーストを検知できませんでした')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def close_all(self) -> bool:
        complete_message = 'Order Filled'
        try:
            # 全て決済 をクリックする
            selector = '#mexc-web-futures-exchange-handle-content-right div[class^="CloseAllPosition_closeAllPosition"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            time.sleep(0.5)
            # モーダルが上がってくるので最終確認処理する
            selector = 'div.ant-modal-content > div.ant-modal-footer > button.ant-btn.ant-btn-primary'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            # 完了メッセージ確認
            selector = 'div.ant-notification-notice-message'
            element = self.wait.until(self.visibility((By.CSS_SELECTOR, selector)))
            if complete_message in element.text.strip():
                print('注文が全て約定しました')
                return True
            else:
                print(f'成功トーストを検知できませんでした')
                return False
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def heartbeat(self) -> bool:
        try:
            # Openタブをクリックする
            selector = 'span[data-testid="contract-trade-order-form-tab-open"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            element.click()
            # Open Long ボタンのクリック可否確認
            selector = 'button[data-testid="contract-trade-open-long-btn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            # Open Short ボタンをクリック可否確認
            selector = 'button[data-testid="contract-trade-open-short-btn"]'
            element = self.wait.until(self.clickable((By.CSS_SELECTOR, selector)))
            return True
        except TimeoutException as e:
            print(f'[TimeoutException] {str(e)}')
            return False
        except Exception as e:
            print(f'[Exception] {str(e)}')
            return False

    def is_position_open(self, side:str) -> bool:
        pass

if __name__ == '__main__':
    bot =SeleniumBot()
    bot.close_all()
    pass