from flask import Flask, request, jsonify
import os
import base64

import boto3
import botocore
import dynamodb_handler as dynamodb
from flask_restx import Api,Resource, fields

import sentry_sdk

from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk import capture_exception




app = Flask(__name__)
api = Api(app, version='1.0',title="Liveness Check API",
        description =  "Verify the liveness of an indiviual"
)


ns = api.namespace('', description="Liveness Check API")

checker = api.model('Checker', {
    'param': fields.String(required=True, enum=['face','mouthOpen','mouthClose','id']),
    'image': fields.String(required=True, description='base64 string of the image to check')
})

matcher = api.model('Match', {
    'selfie_image': fields.String(required=True, description='base64 string of the selfie image'),
    'photoid_image': fields.String(required=True, description='base64 string of the photo id')
})



res_data =  api.model('Res', {
    'match': fields.Boolean(description='Result of the image validation')
})



ver_data =  api.model('Ver', {
    'match': fields.Boolean(description='Result of the image validation'),
    'confidence_value': fields.Integer()
})

checker_res = api.model('Checker_res', {
    'entity': fields.Nested(res_data, description= 'The response from operation')
})

error_model =  api.model('error_model', {
    'error': fields.String,
})

m_data  = api.model('Mat', {
    'match': fields.Boolean(description='Result of the image validation'),
    'confidence_value': fields.Integer()
})

m_data_selfie = api.model('Mat_selfie',{
    'selfie': fields.Nested(m_data, description='The response of the data')
})

m_data_selfie_res =  api.model('Mat_selfie_res', {
    'entity': fields.Nested(m_data_selfie, description = 'Response')
})

# Parser for /check
parser = api.parser()
parser.add_argument('image', type=str, required=True, help='The base64 string of the image,',location='json')
parser.add_argument('session_id', type=str, required=True, help='The Session Id,',location='json')
parser.add_argument('app_id', type=str, required=True, help='The App id,',location='json')
parser.add_argument('param', type=str, required=True, help='face|mouthOpen|mouthClose|id,',location='json')

#Parser for /match

m_parser  =  api.parser()
m_parser.add_argument('selfies',type=bool, required=False,help='Indicates selfies only', location='json')
m_parser.add_argument('selfie_image', type=str, required=True, help='The base 64 string og the selfie image', location='json')
m_parser.add_argument('photoid_image', type=str, required=True, help= 'The base 64 string of the photo id image',location='json')


@app.route('/')
def root_route():
    try:
        dynamodb.CreateTableVerification()
        return "Table created"
    except:
        return "Table existing"


@api.errorhandler
def default_error_handler(e):
    message = 'An error occurred from our end, we are on it'

    return {'error': message, 'trace': str(e)},500


    
@ns.route('/verify' )
class Verification(Resource):
    """ Gets the verification result associated with the session_id """

    @api.doc(params= {'session_id': 'The session Id', 'id': 'Indicates if validation should include ID'})
    @api.response(400, 'Bad request',error_model)
    @api.response(200,'Success', checker_res)
    def get(self):
        """Gets the verification result associated with the session_id """

        
        session_id  = ""
        param_id =  ""
        try:
            session_id = request.args.get('session_id')
            param_id =  request.args.get('id')
            if not session_id:
                response  = {"error": "The parameter session_id is missing"}
                return response,400
        except Exception as e:
            response  = {"error": "The parameter session_id is missing"}
            return response,400
            
        try:
            client = boto3.client(
                'rekognition',
            region_name =os.environ.get("REGION_NAME"),
            aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            )

            if param_id is None:
                param_id = False
            elif param_id.lower() == 'true':
                param_id = True
            else:
                param_id = False

          # verify image exists
            id_resp = self.load_image('id',session_id) if param_id else None
            face_resp =  self.load_image('face',session_id)



            if param_id and id_resp is not True:
                return id_resp, 400
            
            if face_resp is not True:
                return face_resp,400

            result = None
            if param_id:
                result  = compare_faces(client, session_id)

            images =self.get_images(session_id)
          
            if result:
                dynamodb.update(session_id,images['id'],'Completed')

            confidences  =  dynamodb.get(session_id)

            
            id = {
                    'url': images['id'],
                    'confidence_value': float(confidences['i_confidence'])
            } if param_id else {}

            o_confidence  = 0

            if not param_id:
                o_confidence = float(confidences['f_confidence'])
            elif  result == False:
                o_confidence = 0
            elif result['Similarity']:
                o_confidence=  result['Similarity']


            
            




            res = {
                'entity' : {
                    'person': {
                        'url': images['face'],
                        'confidence_value': float(confidences['f_confidence'])
                    },
                    'id': id,
                    'overall':{
                        'confidence_value': o_confidence,
                       
                    }
                }
            }
            

            
            return res,200
        except Exception as e:
            response =  {'error': "An error occurred while verifiying, please try again"}

            
            return response,500

    
    def get_images(self, session_id):
        bucket_name = 'dojah-image-rekognition'
        file_name  =  session_id + 'id' + '.jpeg'
        face_name = session_id + 'face' + '.jpeg'
        location= boto3.client('s3').get_bucket_location(Bucket=bucket_name)['LocationConstraint']
        object_url = "https://%s.s3-%s.amazonaws.com/%s" % (bucket_name,location, file_name)
        face_url = "https://%s.s3-%s.amazonaws.com/%s" % (bucket_name,location, face_name)

        return {'face': face_url, 'id': object_url}
    
    def load_image(self,param, session_id):
        try:
            s3  =  boto3.resource('s3')
            s3.Object('dojah-image-rekognition',session_id + param +'.jpeg').load()
            return True
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                response =  {'error': 'No {} data found for this session, please retry verification again'.format(param)}
                return response
            else:
                response  = {'error': "An error occurred while retrieving the {} data, please  re-try verification".format(param)}
                return response
        

        
            
            
@ns.route('/match')
class Match(Resource):
    """ Finds a match between two images - selfie vs passport """

    @api.doc(parser=m_parser)
    @ns.expect(matcher)
    @api.response(400, 'Bad request',error_model)
    @api.response(200, 'Success', m_data_selfie_res)

    def post(self):
        selfie = ""
        photo = ""


        try:
            try:
                data  =  request.get_json(force=True)
            except Exception as e:
                return {'error': "An error occurred while passing your input, please make sure your request is JSON formatted"},400
            
            selfie =  data['selfie_image']
            photo =  data['photoid_image']
        except Exception as e:
            response =  {"error": "The parameter {} is missing".format(str(e))}
            #capture_exception(e)

            return response, 400
        
        selfie_data =  None
        photo_data = None


        try:
            selfie_data =  base64.b64decode(str(selfie))
            photo_data =  base64.b64decode(str(photo))
        except Exception as e:
            response = {"error": "Error decoding the base64 string, please check the string and try again"}
            #capture_exception(e)
            return response,400

        try:
            client = boto3.client(
                'rekognition',
            region_name =os.environ.get("REGION_NAME"),
            aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            ) 


            resp =  client.compare_faces(
                SourceImage={  'Bytes': selfie_data},
                TargetImage= {'Bytes': photo_data}

            )

            m_res = False
            m_confidence  = 0
            if resp['FaceMatches'] and len(resp['FaceMatches']) > 0:
                m_res = True
                m_confidence = resp['FaceMatches'][0]['Similarity']

            else:
                m_res = False
                m_confidence = 0
            
            res =  {
                'entity': {
                    'selfie': {
                        'match': m_res,
                         'confidence_value': m_confidence
                    }
                   
                }
            }

            return res
        except Exception as e:
            #capture_exception(e)
            return {'error': "An error occurred while completing your request, Please try again"},400


@ns.route('/check' )
class Check(Resource):
    """validate the image request """


    @api.doc(parser=parser)
    @ns.expect(checker)
    @api.response(400, 'Bad request',error_model)
    @api.response(200, 'Success', checker_res)
    def post(self):

        imgstring =""
        param = ""

        try:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                return {'error': "An error occurred while passing your input, please make sure your request is JSON formatted"},400
            imgstring =  data['image']
            param  =  data['param']
            session_id = data['session_id']
            app_id = data['app_id']
        except Exception as e:
            response  = {"error": "The parameter {} is missing".format(str(e))}
            return response,400
        
        imgdata =  None

        params = ['face','id','mouthOpen','mouthClose']

        if param not in params:
            response  = {"error": "Param should be one of face | id | mouthOpen | mouthClose"}

            return response,400

        try:
            imgdata =  base64.b64decode(str(imgstring))
        except Exception as e:
            response = {"error": "Error decoding the base64 string, please check the string and try again"}
            return response,400
        

        try:
            client = boto3.client(
                'rekognition',
            region_name =os.environ.get("REGION_NAME"),
            aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key= os.environ.get("AWS_SECRET_ACCESS_KEY")
            )

            
            result  = detectface(client,imgdata,param,session_id,app_id)
            response =  {'entity': {'match': result}}

            return response,200
        except Exception as e:
            response =  {'error': str(e)}

            return response,400
        

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

    if len(result['FaceDetails']) != 1:
        return False;

    
    if param ==  'face' and result['FaceDetails'] :
        resp =  True
    if param == 'mouthOpen':
        resp = result['FaceDetails'][0]['MouthOpen']['Value']
    if param  ==  'mouthClose':
        a = result['FaceDetails'][0]['MouthOpen']['Value']
        resp =  not a
    
    #write to database if resp = True
    import json
    from decimal import Decimal
   
    if resp and param == 'face':
        url = upload(imagedata,session_id=session_id,id="face")
        dynamodb.addItemToLiveNess(session_id,app_id,url,"",json.loads(json.dumps(result),parse_float=Decimal), Decimal(str(result['FaceDetails'][0]['Confidence'])))

    return resp
def detect_id(client, imagedata, session_id, app_id):

    response =  client.detect_labels(
        Image = {'Bytes': imagedata}
    )
    
    count  = 0
    names  = {}
    confidence = 0
    for label in response["Labels"]:
        names[label['Name']] = label['Confidence']
        confidence = confidence + label['Confidence']

    div =  len(response['Labels']) if len(response['Labels']) > 0 else 1
    confidence =  confidence / div

    
    if "Id Cards" in names or "Document" in names:
        count = count + 1
        if names['Id Cards'] < 90:
            return False
    
    if "Human" in names or "Person" in names:
        count = count +1

        if names['Person'] < 90:
            return False
    
    if "Text" in names:
        count = count + 1
    
    from decimal import Decimal
    if count == 3:
        dynamodb.update_confidence(session_id,'i_confidence',Decimal(str(confidence)))
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

    if resp['FaceMatches'] and len(resp['FaceMatches']) > 0:
        return resp['FaceMatches'][0]
    else:
        return False


if __name__ == '__main__':
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0',port=port)
