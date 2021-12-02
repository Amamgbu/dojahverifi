from flask import app
import boto3
import os

client = boto3.client(
                'dynamodb',
              region_name =os.environ.get("REGION_NAME"),
              aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
              aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            )
resource = boto3.resource(
                 'dynamodb',
              region_name =os.environ.get("REGION_NAME"),
              aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
              aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
)

def CreateTableVerification():
    client.create_table(
        AttributeDefinitions = [
            {
                'AttributeName': 'session_id',
                'AttributeType': 'S'
            }
        ],
        TableName  = 'Liveness_demo',
        KeySchema = [
            {
                'AttributeName':'session_id',
                'KeyType': 'HASH'
            }
        ],
        BillingMode = 'PAY_PER_REQUEST'
    )

LiveTable  = resource.Table('Liveness_demo')
    
def addItemToLiveNess(session_id, app_id, face_url, id_url, body):
        response  =  LiveTable.put_item(
            Item = {
                'session_id': session_id,
                'app_id': app_id,
                'url':  face_url,
                'id_url': id_url,
                'body': "body",
                'status': 'started'
            }
        )

        return response

def get(session_id):
        response  = LiveTable.get_item(
            Key = {
                'session_id': session_id
            },
            AttributesToGet= [
                'url'
            ]
        )

        if(response['ResponseMetadata']['HTTPStatusCode'] == 200):
            if('Item' in response):
                return response['Item']

        return response
def update(session_id, id_url, status):
        response  =  LiveTable.update_item(
            Key = {
                'session_id': session_id
            },
            AttributeUpdates={
                'id_url': {
                    'Value': id_url,
                    'Action': 'PUT'
                },
                'status' : {
                    'Value': status,
                    'Action': 'PUT'
                }
            },

            ReturnValues = "UPDATED_NEW"
        )

        return response