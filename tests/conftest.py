import json
import pytest

@pytest.fixture
def event_no_message():
    return {
        u'Records': [
            {
                u'EventVersion': u'1.0',
                u'EventSubscriptionArn': u'arn:aws:sns:eu-west-1:271871120138:ecs-container-drainer:ee13e8e3-3c62-4094-a553-ffa1707f599b',
                u'EventSource': u'aws:sns',
                u'Sns': {
                    u'SignatureVersion': u'1',
                    u'Timestamp': u'2018-01-05T14:40:46.090Z',
                    u'Signature': u'd6Rk9dAYBDBxowg/RT/e7umdSvPV/MfqBmoEFk13Csj6XiKbi7B1cu1QF256KVaHUNGCHcL4dCWIUxBrSvL/oSXNC3XviUxMC4CuLKLhANdQ+12ZAmFrq149HiLPoz9VCeKyawm14Inrh10qkwk3g7sRwfG3jyiDn0Br8tiBB+72d+plKwCa/sW8EbaCmwgDgqU8Qf9mwKEcQ0pJ66XjG1QWDji+3ywwxKtNHbEnfPje672GJYcBNGZU1+ZedGdjD9CGBcGquH9y65XpS2hxxmXQRjlWCiAkM1uWHjb6qL+rvkPHTbGCD2nwP0sw6OQHb1TCttwnU04yrhiUgQTLrg==',
                    u'SigningCertUrl': u'https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-433026a4050d206028891664da859041.pem',
                    u'MessageId': u'981260d8-7d7f-516d-8ddf-3211edd1ff12',
                    u'Message': None,
                    u'MessageAttributes': {},
                    u'Type': u'Notification',
                    u'UnsubscribeUrl': u'https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:271871120138:ecs-container-drainer:ee13e8e3-3c62-4094-a553-ffa1707f599b',
                    u'TopicArn': u'arn:aws:sns:eu-west-1:271871120138:ecs-container-drainer',
                    u'Subject': u'Re-invoking myself'
                }
            }
        ]
    }

@pytest.fixture
def message():
    return {
        u'EC2InstanceId': u'EC2InstanceIdFromMessage',
        u'Service': u'AWS Auto Scaling',
        u'AutoScalingGroupName': u'ecs-testing-dev-1-ECSAutoScalingGroup-HHMT99DL02F9',
        u'LifecycleActionToken': u'9977f116-f9a8-4149-ae60-711742003003',
        u'LifecycleHookName': u'ecs-testing-dev-1-ASGTerminateHook-19A75XFO08VR7',
        u'RequestId': u'25d5831b-1149-ea51-02d2-bbfc4c211e82',
        u'Time': u'2018-01-05T14:40:44.682Z',
        u'LifecycleTransition': u'autoscaling:EC2_INSTANCE_TERMINATING',
        u'AccountId': u'271871120138'
    }

@pytest.fixture
def cache():
    return {
        '_CidLambdaCache': {
            'InstanceIsDraining': True,
            'EcsCluster': 'EcsClusterFromCache',
            'ContainerInstanceArn': 'ContainerInstanceArnFromCache',
        }
    }

@pytest.fixture
def event_no_cache(event_no_message, message):
    event_no_message['Records'][0]['Sns']['Message'] = json.dumps(message)
    return event_no_message

@pytest.fixture
def event_with_cache(event_no_message, message, cache):
    message.update(cache)
    event_no_message['Records'][0]['Sns']['Message'] = json.dumps(message)
    return event_no_message
