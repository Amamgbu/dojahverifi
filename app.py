from logging import debug
from types import resolve_bases
from flask import Flask, request, jsonify
import os
import base64
import boto3
import dynamodb_handler as dynamodb

app = Flask(__name__)

@app.route('/')
def root_route():
    dynamodb.CreateTableVerification()
    return "Created"



@app.route('/verify',methods=['GET'])
def verify():
    if request.method == 'GET':
        session_id  = ""
        try:
            session_id = request.args.get('session_id')
        except Exception as e:
            response  = {"error": "There appears to be an error with the paramters in your request", "trace": str(e)}
            return jsonify(response),400
        
        try:
            client = boto3.client(
                'rekognition',
              region_name =os.environ.get("REGION_NAME"),
              aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
              aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            )

            
            result  = compare_faces(client, session_id)
            bucket_name = 'dojah-image-rekognition'
            file_name  =  session_id + 'id' + '.jpeg'
            location= boto3.client('s3').get_bucket_location(Bucket=bucket_name)['LocationConstraint']
            object_url = "https://%s.s3-%s.amazonaws.com/%s" % (bucket_name,location, file_name)
            if result:
                dynamodb.update(session_id,object_url,'Completed')

            response =  {'match': result}

            return jsonify(response)
        except Exception as e:
            response =  {'error': 'An error occured', 'trace': str(e)}

            return jsonify(response),500

@app.route('/check',methods=['POST'])
def check():
    if request.method == 'POST':
        imgstring =""
        param = ""

        try:
            data = request.get_json(force=True)
            imgstring =  data['image']
            param  =  data['param']
            session_id = data['session_id']
            app_id = data['app_id']
        except Exception as e:
            response  = {"error": "There appears to be an error with the paramters in your request", "trace": str(e)}
            return jsonify(response),400
        
        imgdata =  None

        try:
            imgdata =  base64.b64decode(str(imgstring))
        except Exception as e:
            response = {"error": "Error decoding the base64 string, please check and try again", "trace": str(e)}
            return jsonify(response),400
        

        try:
            client = boto3.client(
                'rekognition',
              region_name =os.environ.get("REGION_NAME"),
              aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
              aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            )

            
            result  = detectface(client,imgdata,param,session_id,app_id)
            response =  {'match': result}

            return jsonify(response)
        except Exception as e:
            response =  {'error': 'An error occured', 'trace': str(e)}

            return jsonify(response),500
        

def upload(imagedata,session_id,id):
    s3 =  boto3.resource('s3')
    bucket_name  = 'dojah-image-rekognition'
    file_name  =  session_id + id + '.jpeg'

    obj  = s3.Object(bucket_name,file_name)
    obj.put(Body=imagedata)
    location  =  boto3.client('s3').get_bucket_location(Bucket=bucket_name)['LocationConstraint']
    object_url = "https://%s.s3-%s.amazonaws.com/%s" % (bucket_name,location, file_name)
    
    return object_url

def detectface(client, imagedata, param, session_id,app_id):
    if param == "id":
        return detect_id(client, imagedata,session_id,app_id=app_id)
    Attributes = []
    resp  =  False
    if param == 'face':
        Attributes  = ['DEFAULT']
    elif param  == 'mouthOpen':
        Attributes = ['ALL']
    elif param == 'mouthClose':
        Attributes = ['ALL']

    result  =  client.detect_faces(
        Image =  {'Bytes': imagedata},
        Attributes = Attributes
    )

    if param ==  'face' and result['FaceDetails'] :
        resp =  True
    if param == 'mouthOpen':
        resp = result['FaceDetails'][0]['MouthOpen']['Value']
    if param  ==  'mouthClose':
        a = result['FaceDetails'][0]['MouthOpen']['Value']
        resp =  not a
    
    #write to database if resp = True

   
    if resp and param == 'face':
        url = upload(imagedata,session_id=session_id,id="face")
        dynamodb.addItemToLiveNess(session_id,app_id,url,"",result)

    return resp
def detect_id(client, imagedata, session_id, app_id):

    response =  client.detect_labels(
        Image = {'Bytes': imagedata}
    )
    
    count  = 0
    names  = []
    for label in response["Labels"]:
        names.append(label['Name'])
    
    if "Id Cards" in names or "Document" in names:
        count = count + 1
    
    if "Human" in names or "Person" in names:
        count = count +1
    
    if "Text" in names:
        count = count + 1
    
    
    if count == 3:
        upload(imagedata,session_id,"id")
        return True
    else:
        return False

def compare_faces(client,session_id):
    """ """
    resp = client.compare_faces(
        SourceImage={
            'S3Object':{
                'Bucket': 'dojah-image-rekognition',
                'Name': session_id + 'face' +'.jpeg'
            }
        },
        TargetImage={
            'S3Object': {
                'Bucket':'dojah-image-rekognition',
                'Name': session_id + 'id'+ '.jpeg'
            }
        }
    )

    if resp['FaceMatches']:
        return True
    else:
        return False


if __name__ == '__main__':
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0',port=port,debug=True)
