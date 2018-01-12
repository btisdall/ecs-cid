from __future__ import print_function
import boto3
from botocore.exceptions import ClientError
import json
import logging
import os
import time


class ContainerInstanceDrainer:

    def __init__(self, event, context):

        logging.basicConfig()
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, os.environ.get('LOGLEVEL', 'WARNING').upper()))
        self.logger = logger

        self.reinvocation_delay = 5

        self.event = event
        self.message = json.loads(event['Records'][0]['Sns']['Message'])
        self.cache = self.message['_CidLambdaCache'] if '_CidLambdaCache' in self.message else {}
        logger.debug("Cache: %s", self.cache)

        session = boto3.session.Session()
        logger.debug("Boto session is in region: %s", session.region_name)

        self.ecs_client = session.client(service_name='ecs')
        self.asg_client = session.client(service_name='autoscaling')
        self.sns_client = session.client(service_name='sns')

    @staticmethod
    def _sleep(s):
        time.sleep(s)

    def search_for_ecs_details(self, ec2_instance_id):
        """
        Given an EC2 instance-id, search all ECS clusters and return a tuple
        consisting of the matching ECS cluster name and container instance ARN
        or an empty tuple if no match found.
        :param ec2_instance_id: EC2 instance-id
        """
        cluster_paginator = self.ecs_client.get_paginator('list_clusters')
        ci_paginator = self.ecs_client.get_paginator('list_container_instances')

        for cluster_page in cluster_paginator.paginate():
            for cluster in cluster_page['clusterArns']:
                for ci_page in ci_paginator.paginate(cluster=cluster):
                    container_instance_arns = ci_page['containerInstanceArns']
                    if not container_instance_arns:
                        continue

                    describe_ci_res = self.ecs_client.describe_container_instances(
                          cluster=cluster, containerInstances=container_instance_arns)

                    for container in describe_ci_res['containerInstances']:
                        if container['ec2InstanceId'] == ec2_instance_id:
                            return (cluster, container['containerInstanceArn'])

        self.logger.info("EC2 instance-id: %s does not appear to be a member of an ECS cluster",
                         ec2_instance_id)
        return ()

    def get_ecs_details(self, ec2_instance_id):
        """
        Given an EC2 instance-id, return a tuple containing the corresponding
        ECS cluster name and container instance ARN
        :param ec2_instance_id: EC2 instance-id
        """
        cache = self.cache

        if 'EcsCluster' in cache and 'ContainerInstanceArn' in cache:
            self.logger.info("Found ECS details in SNS message")
            return(cache['EcsCluster'], cache['ContainerInstanceArn'])

        self.logger.info("ECS details not in message so searching clusters for match...")
        return self.search_for_ecs_details(ec2_instance_id)

    def set_draining(self, cluster, container_instance_arn):
        """Set a container instance state to DRAINING
           :param cluster: ECS cluster of which ECS container instance of interest is a member
           :param container_instance_arn: ECS container instance ARN
        """
        logger = self.logger

        if self.cache.get('InstanceIsDraining'):
            logger.info("Container instance: %s previously set to draining", container_instance_arn)
            return

        logger.info(
            "Setting status of container instance: %s to DRAINING...", container_instance_arn)

        self.ecs_client.update_container_instances_state(
            cluster=cluster, containerInstances=[container_instance_arn], status='DRAINING',
        )

        self.cache['InstanceIsDraining'] = True

    def get_running_tasks(self, cluster, container_instance_arn):
        """Return a list of tasks running on a container instance.
           :param cluster: ECS cluster of which ECS container instance of interest is a member
           :param container_instance_arn: ECS container instance ARN
        """
        logger = self.logger

        list_tasks_response = self.ecs_client.list_tasks(
                cluster=cluster, containerInstance=container_instance_arn)

        logger.debug("Task list for container instance: %s: %s",
                     container_instance_arn, list_tasks_response['taskArns'])

        running_tasks = list_tasks_response['taskArns']

        logger.debug("Container instance: %s has tasks: %s", container_instance_arn, running_tasks)

        return running_tasks

    def complete_hook(self, **kwargs):
        logger = self.logger
        try:
            response = self.asg_client.complete_lifecycle_action(**kwargs)
            logger.info("Response received from complete_lifecycle_action: %s", response)
            logger.info("Completed lifecycle hook action")
        except ClientError as e:
            logger.error("Client error attempting to complete lifecycle hook: %s", e)
        except Exception as e:
            logger.error("Unknown error attempting to complete lifecycle hook: %s", e)

    def run(self):
        logger = self.logger
        message = self.message

        logger.info("Lambda received the event %s", self.event)

        asg_name = message['AutoScalingGroupName']
        topic_arn = self.event['Records'][0]['Sns']['TopicArn']

        if not ('LifecycleTransition' in message and
                message['LifecycleTransition'] == 'autoscaling:EC2_INSTANCE_TERMINATING'):
            logger.info("Ignoring non-EC2_INSTANCE_TERMINATING message")
            return

        ec2_instance_id = message['EC2InstanceId']
        logger.info("Received termination notification for EC2 instance-id: %s, ASG: %s",
                    ec2_instance_id, asg_name)

        cluster, container_instance_arn = self.get_ecs_details(ec2_instance_id)
        logger.info(
            "EC2 instance-id: %s appears to be container instance ARN: %s, belonging to ECS cluster: %s",
            ec2_instance_id, container_instance_arn, cluster
        )

        lifecycle_hook_name = message['LifecycleHookName']
        logger.debug("Lifecycle hook name is %s", lifecycle_hook_name)

        self.set_draining(cluster, container_instance_arn)

        logger.info("Checking for running tasks...")
        tasks_running = self.get_running_tasks(cluster, container_instance_arn)
        logger.debug("Running tasks: %s", tasks_running)

        if len(tasks_running) > 0:

            logger.info("There are still running tasks on %s, invoking myself again to re-check",
                        container_instance_arn)

            cache = self.cache
            cache['EcsCluster'], cache['ContainerInstanceArn'] = cluster, container_instance_arn
            message['_CidLambdaCache'] = cache

            self.logger.info("Publishing to SNS topic: %s after %s seconds...",
                             topic_arn, self.reinvocation_delay)

            self._sleep(self.reinvocation_delay)

            self.sns_client.publish(TopicArn=topic_arn, Message=json.dumps(message),
                                    Subject='Re-invocation')
            return

        logger.info("No tasks are running on instance %s, completing lifecycle action...",
                    ec2_instance_id)

        self.complete_hook(LifecycleHookName=lifecycle_hook_name,
                           AutoScalingGroupName=asg_name,
                           LifecycleActionResult='CONTINUE',
                           InstanceId=ec2_instance_id)
