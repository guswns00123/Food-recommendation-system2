import boto3
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.hooks.base_hook import BaseHook
import pendulum
from airflow.exceptions import AirflowFailException
import timedelta

def trigger_lambda(**kwargs):
    # boto3 클라이언트를 이용한 Lambda 호출
    session = boto3.Session(
        aws_access_key_id=BaseHook.get_connection('aws_lambda').login,
        aws_secret_access_key=BaseHook.get_connection('aws_lambda').password,
        region_name='ap-northeast-2'
    )
    
    client = session.client('lambda')
    response = client.invoke(
        FunctionName='TFT_data_S3',
        InvocationType='RequestResponse',  # 'Event'는 비동기 호출
        Payload=b'{}'
    )
    kwargs['ti'].xcom_push(key='lambda_response', value=response)
    

def check_lambda_status(**kwargs):
    # XCom에서 Lambda 호출 결과 가져오기
    ti = kwargs['ti']
    lambda_result = ti.xcom_pull(task_ids='trigger_lambda')

    status = lambda_result['status']
    status_code = lambda_result['status_code']

    # Lambda 호출 성공 여부에 따른 처리
    if status == 'success':
        print(f"Lambda function executed successfully with status code {status_code}")
    else:
        raise AirflowFailException(f"Lambda function failed with status code {status_code}")
# def load_data_from_s3(**kwargs):
#     # S3 클라이언트 생성
#     s3_client = boto3.client('s3')

#     # S3에서 버킷과 파일 경로 지정
#     bucket_name = 'morzibucket'
#     object_key = 'path/to/your/file.csv'
    
#     # 파일을 로컬로 다운로드
#     local_file_path = '/tmp/file.csv'
    
#     # S3에서 파일 다운로드
#     s3_client.download_file(bucket_name, object_key, local_file_path)
    
#     print(f"Downloaded {object_key} from S3 bucket {bucket_name} to {local_file_path}")
with DAG(
    dag_id='dag_lambda_trigger',
    start_date=pendulum.datetime(2024,10,1, tz='Asia/Seoul'), 
    schedule='0 */6 * * *',  # 매일 6시간마다 실행
    catchup=False
) as dag:
    # Lambda 호출 작업 정의
    trigger_lambda_task = PythonOperator(
        task_id='trigger_lambda',
        python_callable=trigger_lambda,
        provide_context=True,
        retries=3,  # 3번 재시도 후 실패하면 넘어가게 설정
        retry_delay=timedelta(minutes=2),  # 재시도 간격 설정
        execution_timeout=timedelta(minutes=10),  # 실행 제한 시간 설정
        trigger_rule='all_done'  # 실패해도 다음 태스크로 넘어가게 설정
    )
    check_lambda_task = PythonOperator(
        task_id='check_lambda_status',
        python_callable=check_lambda_status,
        provide_context=True,
    )

    # Task 순서 정의
    trigger_lambda_task >>check_lambda_task