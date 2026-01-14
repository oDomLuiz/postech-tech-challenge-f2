import logging
import sys
from datetime import datetime
from typing import List, Optional

import boto3
from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql.functions import col, datediff, lit, regexp_replace, sum, to_date

# Configurações
CONFIG = {
    "raw_bucket": "fiap-luiz-mlet",
    "raw_prefix": "raw/b3_data/",
    "output_path": "s3://fiap-luiz-mlet/refined/b3_data/",
    "partition_keys": ["data_referencia", "acao"],
    "date_format": "%Y-%m-%d",
}


class GlueETL:
    """Classe responsável pelo ETL no AWS Glue."""

    def __init__(self, glue_context: GlueContext, spark_session, config: dict):
        self.glue_context = glue_context
        self.spark = spark_session
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.s3_client = boto3.client('s3')

    def get_partitions(self) -> List[str]:
        """Obtém as partições disponíveis no S3."""
        response = self.s3_client.list_objects_v2(
            Bucket=self.config["raw_bucket"],
            Prefix=self.config["raw_prefix"],
            Delimiter='/'
        )
        prefixes = [obj['Prefix'] for obj in response.get('CommonPrefixes', [])]
        partitions = set()
        for prefix in prefixes:
            if "=" in prefix:
                part = prefix.split("/")[-2]
                partitions.add(part)
        sorted_partitions = sorted(partitions, reverse=True)
        if not sorted_partitions:
            raise ValueError("Nenhuma partição encontrada no S3.")
        self.logger.info(f"Partições encontradas: {sorted_partitions}")
        return sorted_partitions

    def fetch_data(self, partition: str):
        """Lê dados de uma partição específica."""
        input_path = f"s3://{self.config['raw_bucket']}/{self.config['raw_prefix']}{partition}"
        dyf = self.glue_context.create_dynamic_frame.from_options(
            format_options={"withHeader": True},
            connection_type="s3",
            format="parquet",
            connection_options={"paths": [input_path]}
        )
        df = dyf.toDF()
        self.logger.info(f"Dados lidos da partição: {partition}")
        return df

    def rename_columns(self, df):
        """Renomeia as colunas do DataFrame."""
        df = (df.withColumnRenamed("Código", "codigo")
              .withColumnRenamed("Ação", "acao")
              .withColumnRenamed("Tipo", "tipo")
              .withColumnRenamed("Qtde. Teórica", "quantidade_teorica")
              .withColumnRenamed("Part. (%)", "participacao_percentual")
              )
        self.logger.info("Colunas renomeadas.")
        return df

    def get_partition_date(self, partition: str) -> datetime.date:
        """Extrai a data da partição."""
        reference_date_str = partition.split('=')[1].split('/')[0].strip()
        return datetime.strptime(reference_date_str, self.config["date_format"]).date()

    def cast_columns(self, df):
        """Converte tipos de colunas."""
        df = (df
              .withColumn("quantidade_teorica", regexp_replace(col("quantidade_teorica"), r"\.", "").cast("long"))
              .withColumn("participacao_percentual", regexp_replace(col("participacao_percentual"), r",", ".").cast("float"))
              )
        self.logger.info("Colunas convertidas.")
        return df

    def add_reference_date(self, df, reference_date: datetime.date):
        """Adiciona coluna de data de referência."""
        df = df.withColumn("data_referencia", lit(reference_date))
        self.logger.info(f"Data de referência adicionada: {reference_date}")
        return df

    def calculate_days_difference(self, df, current_date: datetime.date, previous_date: Optional[datetime.date]):
        """Calcula diferença de dias para a última data de referência."""
        if previous_date is None:
            df = df.withColumn("quantidade_dias_ultima_data_referencia", lit(0))
        else:
            df = df.withColumn("quantidade_dias_ultima_data_referencia", datediff(col("data_referencia"), lit(previous_date)))
        self.logger.info("Diferença de dias calculada.")
        return df

    def aggregate_data(self, df):
        """Agrega dados por ação e calcula totais."""
        df_grouped = (
            df.groupBy("acao")
            .agg(
                sum("quantidade_teorica").alias("quantidade_teorica_acao"),
                sum("participacao_percentual").alias("participacao_percentual_acao")
            )
        )
        quantidade_teorica_total = df.agg(sum("quantidade_teorica").alias("quantidade_teorica_total")).collect()[0][0]
        df = df.withColumn("quantidade_teorica_total", lit(quantidade_teorica_total))
        df = (df
              .join(df_grouped, on="acao", how='inner')
              .select(
                  "codigo",
                  df.acao.alias("acao"),
                  "tipo",
                  "quantidade_teorica",
                  "participacao_percentual",
                  "quantidade_teorica_total",
                  "quantidade_teorica_acao",
                  "participacao_percentual_acao",
                  "quantidade_dias_ultima_data_referencia",
                  "data_referencia"
              )
              )
        self.logger.info("Dados agregados.")
        return df

    def save_data(self, df):
        """Salva os dados processados no S3."""
        dyf = DynamicFrame.fromDF(df, self.glue_context, "dyf")
        self.glue_context.write_dynamic_frame.from_options(
            frame=dyf,
            connection_type="s3",
            format="parquet",
            connection_options={"path": self.config["output_path"], "partitionKeys": self.config["partition_keys"]}
        )
        self.logger.info(f"Dados salvos em: {self.config['output_path']}")

    def run_etl(self):
        """Executa o pipeline ETL completo."""
        try:
            partitions = self.get_partitions()
            df = self.fetch_data(partitions[0])
            df = self.rename_columns(df)
            reference_date = self.get_partition_date(partitions[0])
            df = self.add_reference_date(df, reference_date)
            df = self.cast_columns(df)
            df.printSchema()

            previous_date = self.get_partition_date(partitions[1]) if len(partitions) > 1 else None
            df = self.calculate_days_difference(df, reference_date, previous_date)
            df = self.aggregate_data(df)
            self.save_data(df)
            self.logger.info("ETL concluído com sucesso.")
        except Exception as e:
            self.logger.error(f"Erro durante ETL: {e}")
            raise


def main():
    """Função principal para o job Glue."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    args = getResolvedOptions(sys.argv, ['JOB_NAME'])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args['JOB_NAME'], args)

    etl = GlueETL(glue_context, spark, CONFIG)
    etl.run_etl()

    job.commit()


if __name__ == "__main__":
    main()