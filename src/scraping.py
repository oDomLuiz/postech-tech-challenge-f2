import logging
import os
from datetime import datetime
from typing import List, Optional

import boto3
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

load_dotenv()
from webdriver_manager.chrome import ChromeDriverManager


# Configurações
CONFIG = {
    "url": "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV?language=pt-br",
    "table_xpath": "/html/body/app-root/app-day-portfolio/div/div/div[1]/form/div[2]/div/table/tbody",
    "pagination_id": "listing_pagination",
    "next_button_selector": "li.pagination-next",
    "disabled_class": "pagination-next disabled",
    "bucket_name": "fiap-luiz-mlet",
    "s3_prefix": "raw/b3_data",
    "local_folder": "b3_data",
    "partition_col": "ano_mes_dia",
    "timeout": 10,
    "headless": True,
}


class B3Scraper:
    """Classe responsável por fazer scraping dos dados da B3."""

    def __init__(self, config: dict):
        self.config = config
        self.driver = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def setup_driver(self) -> webdriver.Chrome:
        """Configura e retorna o driver do Chrome."""
        options = webdriver.ChromeOptions()
        if self.config.get("headless", True):
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.logger.info("Driver Chrome configurado.")
        return self.driver

    def fetch_table_data(self, content: List[List[str]]) -> List[List[str]]:
        """Extrai dados da tabela atual."""
        try:
            wait = WebDriverWait(self.driver, timeout=self.config["timeout"])
            table = wait.until(EC.visibility_of_element_located((By.XPATH, self.config["table_xpath"])))

            table_rows = table.find_elements(By.TAG_NAME, 'tr')

            for row in table_rows:
                columns = row.find_elements(By.TAG_NAME, 'td')
                if columns:
                    content.append([col.text for col in columns])

            self.logger.info(f"Extraídos {len(table_rows)} linhas da tabela.")
            return content

        except Exception as e:
            self.logger.error(f"Erro ao extrair dados da tabela: {e}")
            raise

    def get_all_pages_data(self) -> List[List[str]]:
        """Navega pelas páginas e coleta todos os dados."""
        content = []
        pagination = self.driver.find_element(By.ID, self.config["pagination_id"])

        while True:
            try:
                content = self.fetch_table_data(content)

                next_button = pagination.find_element(By.CSS_SELECTOR, self.config["next_button_selector"])

                if self.config["disabled_class"] in next_button.get_attribute('class'):
                    break

                button_link = next_button.find_element(By.TAG_NAME, 'a')
                ActionChains(self.driver).move_to_element(button_link).click().perform()
                self.logger.info("Navegou para a próxima página.")

            except Exception as e:
                self.logger.error(f"Erro ao navegar pelas páginas: {e}")
                break

        return content

    def get_headers(self) -> List[str]:
        """Extrai os cabeçalhos da tabela."""
        table = self.driver.find_element(By.TAG_NAME, 'table')
        headers = [header.text for header in table.find_elements(By.XPATH, ".//thead//th")]
        self.logger.info(f"Cabeçalhos extraídos: {headers}")
        return headers

    def scrape(self) -> pd.DataFrame:
        """Executa o scraping completo e retorna um DataFrame."""
        self.setup_driver()
        self.driver.get(self.config["url"])
        headers = self.get_headers()
        data = self.get_all_pages_data()
        df = pd.DataFrame(data, columns=headers)
        self.logger.info(f"DataFrame criado com {len(df)} linhas.")
        return df

    def close(self):
        """Fecha o driver."""
        if self.driver:
            self.driver.quit()
            self.logger.info("Driver fechado.")


class DataProcessor:
    """Classe responsável por processar os dados extraídos."""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_date_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adiciona coluna de data ao DataFrame."""
        today = datetime.today().strftime("%Y-%m-%d")
        df[self.config["partition_col"]] = today
        self.logger.info(f"Coluna '{self.config['partition_col']}' adicionada com valor {today}.")
        return df

    def save_to_parquet(self, df: pd.DataFrame) -> str:
        """Salva o DataFrame em Parquet particionado."""
        today = datetime.today().strftime("%Y-%m-%d")
        df.to_parquet(
            self.config["local_folder"],
            engine="pyarrow",
            partition_cols=[self.config["partition_col"]]
        )
        self.logger.info(f"Dados salvos em Parquet no diretório '{self.config['local_folder']}'.")
        return today


class S3Uploader:
    """Classe responsável por fazer upload dos dados para S3."""

    def __init__(self, config: dict):
        self.config = config
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('ACCESS_KEY'),
            aws_secret_access_key=os.getenv('SECRET_KEY'),
            aws_session_token=os.getenv('SESSION_TOKEN')
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def upload_files(self, date: str):
        """Faz upload dos arquivos Parquet para S3."""
        local_path_partition = os.path.join(self.config["local_folder"], f"ano_mes_dia={date}")

        if not os.path.exists(local_path_partition):
            self.logger.warning(f"Diretório {local_path_partition} não encontrado.")
            return

        for file in os.listdir(local_path_partition):
            if file.endswith(".parquet"):
                local_file_path = os.path.join(local_path_partition, file)
                s3_file_path = f"{self.config['s3_prefix']}/ano_mes_dia={date}/{file}"

                try:
                    self.s3_client.upload_file(local_file_path, self.config["bucket_name"], s3_file_path)
                    self.logger.info(f"Arquivo {file} enviado para S3: {s3_file_path}")
                except Exception as e:
                    self.logger.error(f"Erro ao enviar {file} para S3: {e}")


def main():
    """Função principal para executar o pipeline de scraping."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    scraper = B3Scraper(CONFIG)
    processor = DataProcessor(CONFIG)
    uploader = S3Uploader(CONFIG)

    try:
        df = scraper.scrape()
        df = processor.add_date_column(df)
        date = processor.save_to_parquet(df)
        uploader.upload_files(date)
        logging.info(f"Extração de dados finalizada com sucesso! Data: {date}")
    except Exception as e:
        logging.error(f"Erro durante a execução: {e}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()