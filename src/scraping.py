from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
import pandas as pd
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import boto3
from datetime import datetime
import os
 
def fetch_table_data(driver, content):
    try:
        wait = WebDriverWait(driver, timeout=5)
        table = wait.until(EC.visibility_of_element_located((By.XPATH, '/html/body/app-root/app-day-portfolio/div/div/div[1]/form/div[2]/div/table/tbody')))

        table_rows = table.find_elements(By.TAG_NAME, 'tr')
        
        for row in table_rows:
            columns = row.find_elements(By.TAG_NAME, 'td')
            if columns:
                content.append([col.text for col in columns])

        return content

    except Exception as e:
        print(f"Error fetching data from Bovespa: {e}")


def get_next_page(driver):
    
    pagination = driver.find_element(By.ID, 'listing_pagination')
    content = []
    
    while True:
        try:
            # obter os dados da tabela            
            content = fetch_table_data(driver, content)

            next_button = pagination.find_element(By.CSS_SELECTOR, 'li.pagination-next')

            if 'pagination-next disabled' in next_button.get_attribute('class'):
                break

            # clica para ir para a proxima pagina se o botao ainda estiver habilitado
            button_link = next_button.find_element(By.TAG_NAME, 'a')
            ActionChains(driver).move_to_element(button_link).click().perform()
            
        except Exception as e:
           print(f"Error fetching data from Bovespa: {e}")
    
    return content


options = webdriver.ChromeOptions()
options.add_argument("--headless")

service = Service(ChromeDriverManager().install())

driver = webdriver.Chrome(service=service, options=options)
driver.get("https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV?language=pt-br")

# headers
table = driver.find_element(By.TAG_NAME, 'table')
headers = [header.text for header in table.find_elements(By.XPATH, ".//thead//th")]


table_content = get_next_page(driver)
df = pd.DataFrame(table_content, columns=headers)

driver.quit()

s3_client = boto3.client('s3')
today = datetime.today().strftime("%Y-%m-%d")
df["ano_mes_dia"] = today

df.to_parquet("dados_bovespa", engine="pyarrow", partition_cols=["ano_mes_dia"])

bucket_name = "fiap-mle-tc2"
local_folder = "dados_bovespa"
s3_prefix = "raw/dados_bovespa"

local_path_partition = os.path.join(local_folder, f"ano_mes_dia={today}")

if os.path.exists(local_path_partition):
    for file in os.listdir(local_path_partition):
        if file.endswith(".parquet"):
            local_file_path = os.path.join(local_path_partition, file)
            s3_file_path = f"{s3_prefix}/ano_mes_dia={today}/{file}" 

            s3_client.upload_file(local_file_path, bucket_name, s3_file_path)


print('Extração de dados finalizada com sucesso! - {today}')