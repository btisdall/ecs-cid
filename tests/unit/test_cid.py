import json
from cid.drainer import ContainerInstanceDrainer
from mock import Mock, MagicMock, patch
from botocore.exceptions import ClientError

@patch('boto3.session.Session')
@patch('logging.getLogger')
class TestCid():
    def test_init_message_has_no_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        assert cid.cache == {}

    def test_init_message_has_cache(self, mock_logger, mock_session, event_with_cache):
        cid = ContainerInstanceDrainer(event_with_cache, None)
        assert cid.cache['EcsCluster'] == 'EcsClusterFromCache'
        assert cid.cache['ContainerInstanceArn'] == 'ContainerInstanceArnFromCache'

    def test_boto_init(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)

        mock_session.assert_called_with()
        mock_session.return_value.client.assert_any_call(service_name='ecs')
        mock_session.return_value.client.assert_any_call(service_name='autoscaling')
        mock_session.return_value.client.assert_any_call(service_name='sns')
        assert mock_session.return_value.client.call_count == 3

    def test_get_ecs_details_no_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)

        cid.cache = {}
        expected = ('my_cluster_1', 'my_ci_1')
        cid.search_for_ecs_details = Mock(return_value=expected)
        rv = cid.get_ecs_details('dummy')

        cid.search_for_ecs_details.assert_called_with('dummy')
        assert rv == expected

    def test_get_ecs_details_with_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)

        cid.cache = dict(EcsCluster='my_cluster_2', ContainerInstanceArn='my_ci_2')
        expected = ('my_cluster_2', 'my_ci_2')
        cid.search_for_ecs_details = Mock()

        rv = cid.get_ecs_details('dummy')
        assert rv == expected
        cid.search_for_ecs_details.assert_not_called()

    def test_search_for_ecs_details(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid.search_for_ecs_details('dummy-id')
        cid.ecs_client.get_paginator.assert_any_call('list_clusters')
        cid.ecs_client.get_paginator.assert_any_call('list_container_instances')

    def test_set_draining_no_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid.cache = {}

        cid.set_draining('SomeCluster', 'SomeCiArn')
        cid.ecs_client.update_container_instances_state.assert_called_with(
                    cluster='SomeCluster',containerInstances=['SomeCiArn'], status='DRAINING')

    def test_set_draining_with_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid.cache = dict(InstanceIsDraining=True)

        cid.set_draining('SomeCluster', 'SomeCiArn')
        cid.ecs_client.update_container_instances_state.assert_not_called()

    def test_get_running_tasks(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)

        expected_tasks = ['task1', 'task2']
        cid.ecs_client.list_tasks = Mock(return_value={'taskArns': expected_tasks})
        rv = cid.get_running_tasks('SomeCluster', 'SomeCiArn')

        cid.ecs_client.list_tasks.assert_called_with(
                cluster='SomeCluster',
                containerInstance='SomeCiArn')
        assert rv == expected_tasks

    def test_complete_hook(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        kwargs = dict(LifecycleHookName='dummy_hook', AutoScalingGroupName='dummy_asg',
                      InstanceId='dummy_instanceid', LifecycleActionResult='DUMMY_ACTION')

        cid.complete_hook(**kwargs)
        cid.asg_client.complete_lifecycle_action.assert_called_with(**kwargs)

        exc = ClientError({}, 'bam!')
        cid.asg_client.complete_lifecycle_action.side_effect = exc
        cid.complete_hook(**kwargs)
        cid.logger.error.assert_called_once_with("Client error attempting to complete lifecycle hook: %s", exc)

        cid.logger.reset_mock()
        exc = Exception('oof!')
        cid.asg_client.complete_lifecycle_action.side_effect = exc
        cid.complete_hook(**kwargs)
        cid.logger.error.assert_called_once_with("Unknown error attempting to complete lifecycle hook: %s", exc)

    def test_run_with_tasks_still_running(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid._sleep = Mock()
        cid.get_ecs_details = Mock(return_value=('SomeCluster', 'SomeCiArn'))
        cid.set_draining = Mock()
        cid.complete_hook = Mock()
        cid.get_running_tasks = Mock(return_value=['task1', 'task2'])
        cid.run()

        cid.get_ecs_details.assert_called_with('EC2InstanceIdFromMessage')
        cid.set_draining.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.get_running_tasks.assert_called_with('SomeCluster', 'SomeCiArn')
        cid._sleep.assert_called_once_with(cid.reinvocation_delay)
        cid.sns_client.publish.assert_called_once()
        cid.complete_hook.assert_not_called()

    def test_run_with_no_tasks_running(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid._sleep = Mock()
        cid.get_ecs_details = Mock(return_value=('SomeCluster', 'SomeCiArn'))
        cid.set_draining = Mock()
        cid.get_running_tasks = Mock(return_value=[])
        cid.complete_hook = Mock()
        cid.run()

        cid.get_ecs_details.assert_called_with('EC2InstanceIdFromMessage')
        cid.set_draining.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.get_running_tasks.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.complete_hook.assert_called()
