import json
from cid.drainer import ContainerInstanceDrainer
from mock import Mock, MagicMock, patch

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
        cid.search_for_ecs_details = MagicMock(return_value=expected)
        rv = cid.get_ecs_details('dummy')

        cid.search_for_ecs_details.assert_called_with('dummy')
        assert rv == expected

    def test_get_ecs_details_with_cache(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)

        cid.cache = dict(EcsCluster='my_cluster_2', ContainerInstanceArn='my_ci_2')
        expected = ('my_cluster_2', 'my_ci_2')
        cid.search_for_ecs_details = MagicMock()

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
        cid.ecs_client.list_tasks = MagicMock(return_value={'taskArns': expected_tasks})
        rv = cid.get_running_tasks('SomeCluster', 'SomeCiArn')

        cid.ecs_client.list_tasks.assert_called_with(
                cluster='SomeCluster',
                containerInstance='SomeCiArn')
        assert rv == expected_tasks

    def test_run_tasks_running(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid.get_ecs_details = MagicMock(return_value=('SomeCluster', 'SomeCiArn'))
        cid.set_draining = MagicMock()
        cid.get_running_tasks = MagicMock(return_value=['task1', 'task2'])
        cid.sns_client = MagicMock()
        cid.run()

        cid.get_ecs_details.assert_called_with('EC2InstanceIdFromMessage')
        cid.set_draining.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.get_running_tasks.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.sns_client.publish.assert_called_once()
        cid.asg_client.complete_lifecycle_action.assert_not_called()

    def test_run_no_tasks_running(self, mock_logger, mock_session, event_no_cache):
        cid = ContainerInstanceDrainer(event_no_cache, None)
        cid.get_ecs_details = MagicMock(return_value=('SomeCluster', 'SomeCiArn'))
        cid.set_draining = MagicMock()
        cid.get_running_tasks = MagicMock(return_value=[])
        cid.sns_client = MagicMock()
        cid.run()

        cid.get_ecs_details.assert_called_with('EC2InstanceIdFromMessage')
        cid.set_draining.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.get_running_tasks.assert_called_with('SomeCluster', 'SomeCiArn')
        cid.sns_client.publish.assert_not_called()
        cid.asg_client.complete_lifecycle_action.assert_called_once()
