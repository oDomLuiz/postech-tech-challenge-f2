import sys
import boto3
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.sql.functions import col, regexp_replace, to_date, lit, sum, datediff
from datetime import datetime

args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

raw_bucket = "fiap-mle-tc2"
raw_prefix = "raw/dados_bovespa/"
output_path = "s3://fiap-mle-tc2/refined/bovespa/"

# obtem os dados
def fetch_data(partition_order):
    input_path = f"s3://{raw_bucket}/{raw_prefix}{sorted_partitions[partition_order]}"
    
    dyf = glueContext.create_dynamic_frame.from_options(
        format_options={"withHeader": True},
        connection_type="s3",
        format="parquet",
        connection_options={"paths": [input_path]}
    )
    return dyf.toDF()

# requisito 5-b: renomear colunas
# renomeia as colunas
def rename_columns(df):
    df = (df.withColumnRenamed("Código", "codigo")
        .withColumnRenamed("Ação", "acao")
        .withColumnRenamed("Tipo", "tipo")
        .withColumnRenamed("Qtde. Teórica", "quantidade_teorica")
        .withColumnRenamed("Part. (%)", "participacao_percentual")
    )
    return df

# obtem a data da particao
def get_partition_date(partition):
    reference_date_str = partition.split('=')[1].split('/')[0].strip()
    return datetime.strptime(reference_date_str, "%Y-%m-%d").date()
    
def cast_columns(df):
    df = (df
        # cast das colunas 
        .withColumn("quantidade_teorica", regexp_replace(col("quantidade_teorica"), r"\.", "").cast("long"))
        .withColumn("participacao_percentual", regexp_replace(col("participacao_percentual"), r",", ".").cast("float"))
    )
    return df

# s3
s3_client = boto3.client('s3')
response = s3_client.list_objects_v2(Bucket=raw_bucket, Prefix=raw_prefix, Delimiter='/')
prefixes = [obj['Prefix'] for obj in response.get('CommonPrefixes', [])]

partitions = set()

for prefix in prefixes:
    if "=" in prefix:
        part = prefix.split("/")[-2]
        partitions.add(part)
        
# particoes em ordem descrescente
sorted_partitions = sorted(partitions, reverse=True) 

if len(sorted_partitions) == 0:
    raise Exception("Nenhuma partição encontrada.")

# obtem os dados da particao mais recente
df = fetch_data(0)

# renomeia as colunas do dataframe
df = rename_columns(df)

# adicao da data de referencia
reference_date = get_partition_date(sorted_partitions[0])
df = df.withColumn("data_referencia", lit(reference_date))

# cast das colunas 
df = cast_columns(df)
df.printSchema()

# requisito 5-c: calculo com datas
if len(sorted_partitions) < 2:
    # nao existem duas particoes (primeiro processamento)
    df = df.withColumn("quantidade_dias_ultima_data_referencia", lit(0))
else:
    previous_partition_reference_date = get_partition_date(sorted_partitions[1])

    # diferenca em dias entre a particao atual e a particao anterior
    df = df.withColumn("quantidade_dias_ultima_data_referencia", datediff(col("data_referencia"), lit(previous_partition_reference_date)))

# requisito 5-a: agrupamento numerico, sumarizacao, contagem ou soma
# soma da quantidade teorica e da participacao_percentual por acao
df_grouped = (
    df.groupBy("acao")
    .agg(
        sum("quantidade_teorica").alias("quantidade_teorica_acao"),
        sum("participacao_percentual").alias("participacao_percentual_acao")
    )
)

# soma da quantidade teorica total
quantidade_teorica_total = df.agg(sum("quantidade_teorica").alias("quantidade_teorica_total")).collect()[0][0]
df = df.withColumn("quantidade_teorica_total", lit(quantidade_teorica_total))

df = (df
    .join(df_grouped, on ="acao", how='inner')
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

## convertendo de volta para DynamicFrame
dyf = DynamicFrame.fromDF(df, glueContext, "dyf")

## salvando os dados no S3
glueContext.write_dynamic_frame.from_options(
    frame=dyf,
    connection_type="s3",
    format="parquet",
    connection_options={"path": output_path, "partitionKeys": ["data_referencia", "acao"]}
)

job.commit()