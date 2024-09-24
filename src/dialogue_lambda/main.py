import json
import os
import boto3

def lambda_handler(event, context):
    if event.get('bot'):
        intent = event['sessionState'].get('intent', {})
        intent_name = intent.get('name', '')
        slots = intent.get('slots', {})
        session_attributes = event.get('sessionState').get('sessionAttributes', {})
        input_transcript = event.get('inputTranscript', '')
        if event.get('invocationSource') == 'DialogCodeHook':
            return lex_build_response(session_attributes, intent, 'ElicitIntent', None, f"Intent identified as {intent_name}")
        else:
            return lex_build_response(session_attributes, intent, 'ElicitIntent', None, 'End of query')


def lex_build_response(attributes, intent, action, slot=None, message=""):
    response = {
        'sessionState': {
            'sessionAttributes': attributes,
            'intent': intent,
            'dialogAction': {
                'type': action,
            }
        }
    }
    if slot:
        response['sessionState']['dialogAction']['slotToElicit'] = slot
    if message:
        response['messages'] = [
            {
                'contentType': 'PlainText',
                'content': message
            }
        ]
    if action == 'ElicitIntent':
        del response['sessionState']['intent']
    return response