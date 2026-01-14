import boto3
import json

def lambda_handler(event, context):
    glue_client = boto3.client('glue')
    
    # Extrair info do evento S3 (opcional, para logging)
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        print(f"Novo arquivo detectado: s3://{bucket}/{key}")
    
    # Iniciar o job Glue
    response = glue_client.start_job_run(JobName='etl_b3')  # Substitua pelo nome real
    print(f"Job Glue iniciado: {response['JobRunId']}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('ETL iniciado via Glue')
    }